-- AI Alpha Research Data Foundation v1
-- Target dialect: PostgreSQL 15+

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE company_master (
    company_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    legal_name TEXT NOT NULL,
    common_name TEXT NOT NULL,
    country_code CHAR(2),
    gics_industry TEXT,
    ai_value_chain_bucket TEXT,
    primary_stage TEXT CHECK (primary_stage IN ('upstream', 'midstream', 'downstream')),
    secondary_segment TEXT,
    secondary_exposure TEXT,
    upstream_dependencies TEXT,
    downstream_customers TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE security_master (
    security_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES company_master(company_id),
    ticker TEXT NOT NULL,
    exchange_mic TEXT NOT NULL,
    currency CHAR(3) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    is_primary_listing BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to >= valid_from),
    UNIQUE (ticker, exchange_mic, valid_from)
);

CREATE INDEX idx_security_company ON security_master(company_id);
CREATE INDEX idx_security_active_ticker ON security_master(exchange_mic, ticker, valid_from, valid_to);

CREATE TABLE metric_definition (
    metric_name TEXT PRIMARY KEY,
    domain TEXT NOT NULL CHECK (domain IN (
        'fundamental', 'estimate', 'product', 'ai_metric', 'valuation', 'feature'
    )),
    description TEXT NOT NULL,
    canonical_unit TEXT,
    higher_is_better BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE market_daily (
    security_id UUID NOT NULL REFERENCES security_master(security_id),
    trade_date DATE NOT NULL,
    revision_seq INTEGER NOT NULL DEFAULT 1 CHECK (revision_seq >= 1),
    close_price NUMERIC(20,6) NOT NULL,
    adjusted_close NUMERIC(20,6) NOT NULL,
    volume NUMERIC(24,4),
    market_cap NUMERIC(24,4),
    free_float_market_cap NUMERIC(24,4),
    realized_vol_20d NUMERIC(18,8),
    beta_252d NUMERIC(18,8),
    available_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_name TEXT NOT NULL,
    source_version TEXT,
    PRIMARY KEY (security_id, trade_date, revision_seq)
);

CREATE INDEX idx_market_pit ON market_daily(security_id, trade_date, available_at DESC);

CREATE TABLE fundamental_observation (
    company_id UUID NOT NULL REFERENCES company_master(company_id),
    metric_name TEXT NOT NULL,
    fiscal_period_end DATE NOT NULL,
    fiscal_period_type TEXT NOT NULL CHECK (fiscal_period_type IN ('FQ', 'FY', 'TTM')),
    metric_value NUMERIC(28,8),
    currency CHAR(3),
    filing_date DATE,
    available_at TIMESTAMPTZ NOT NULL,
    revision_seq INTEGER NOT NULL DEFAULT 1 CHECK (revision_seq >= 1),
    value_status TEXT NOT NULL DEFAULT 'reported' CHECK (value_status IN ('reported', 'restated', 'estimated')),
    source_name TEXT NOT NULL,
    source_record_id TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, metric_name, fiscal_period_end, fiscal_period_type, available_at)
);

CREATE INDEX idx_fundamental_pit
    ON fundamental_observation(company_id, metric_name, fiscal_period_end, available_at DESC);

CREATE TABLE estimate_observation (
    company_id UUID NOT NULL REFERENCES company_master(company_id),
    estimate_metric TEXT NOT NULL,
    forecast_period_end DATE NOT NULL,
    forecast_period_type TEXT NOT NULL CHECK (forecast_period_type IN ('FQ', 'FY', 'NTM')),
    as_of_date DATE NOT NULL,
    estimate_mean NUMERIC(28,8),
    estimate_median NUMERIC(28,8),
    estimate_stddev NUMERIC(28,8),
    analyst_count INTEGER CHECK (analyst_count IS NULL OR analyst_count >= 0),
    currency CHAR(3),
    source_name TEXT NOT NULL,
    source_version TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, estimate_metric, forecast_period_end, forecast_period_type, as_of_date)
);

CREATE INDEX idx_estimate_pit
    ON estimate_observation(company_id, estimate_metric, as_of_date DESC, forecast_period_end);

CREATE TABLE product_master (
    product_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES company_master(company_id),
    product_name TEXT NOT NULL,
    product_type TEXT NOT NULL CHECK (product_type IN (
        'web_app', 'mobile_app', 'api', 'developer_tool', 'model_hub', 'other'
    )),
    valid_from DATE NOT NULL,
    valid_to DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE INDEX idx_product_company ON product_master(company_id, valid_from, valid_to);

CREATE TABLE product_observation (
    product_id UUID NOT NULL REFERENCES product_master(product_id),
    metric_name TEXT NOT NULL,
    observation_start DATE,
    observation_end DATE NOT NULL,
    geo_code TEXT NOT NULL DEFAULT 'GLOBAL',
    metric_value NUMERIC(28,8),
    unit TEXT,
    coverage_ratio NUMERIC(8,6) CHECK (coverage_ratio IS NULL OR coverage_ratio BETWEEN 0 AND 1),
    available_at TIMESTAMPTZ NOT NULL,
    source_name TEXT NOT NULL,
    source_version TEXT NOT NULL DEFAULT 'unknown',
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, metric_name, observation_end, geo_code, available_at),
    CHECK (observation_start IS NULL OR observation_start <= observation_end)
);

CREATE INDEX idx_product_obs_pit
    ON product_observation(product_id, metric_name, observation_end, available_at DESC);

CREATE TABLE ai_entity_master (
    ai_entity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES company_master(company_id),
    product_id UUID REFERENCES product_master(product_id),
    entity_type TEXT NOT NULL CHECK (entity_type IN ('model', 'api', 'repository', 'organization', 'dataset')),
    entity_name TEXT NOT NULL,
    external_id TEXT,
    valid_from DATE NOT NULL,
    valid_to DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to >= valid_from),
    UNIQUE (entity_type, entity_name, valid_from)
);

CREATE INDEX idx_ai_entity_company ON ai_entity_master(company_id);

CREATE TABLE ai_metric_observation (
    ai_entity_id UUID NOT NULL REFERENCES ai_entity_master(ai_entity_id),
    metric_name TEXT NOT NULL,
    observation_start DATE,
    observation_end DATE NOT NULL,
    metric_value NUMERIC(28,8),
    unit TEXT NOT NULL,
    benchmark_name TEXT NOT NULL DEFAULT '',
    measurement_method TEXT,
    available_at TIMESTAMPTZ NOT NULL,
    source_name TEXT NOT NULL,
    source_version TEXT NOT NULL DEFAULT 'unknown',
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ai_entity_id, metric_name, observation_end, benchmark_name, available_at),
    CHECK (observation_start IS NULL OR observation_start <= observation_end)
);

CREATE INDEX idx_ai_metric_pit
    ON ai_metric_observation(ai_entity_id, metric_name, observation_end, available_at DESC);

CREATE TABLE valuation_observation (
    security_id UUID NOT NULL REFERENCES security_master(security_id),
    metric_name TEXT NOT NULL,
    trade_date DATE NOT NULL,
    denominator_period TEXT NOT NULL DEFAULT 'NA',
    metric_value NUMERIC(28,8),
    available_at TIMESTAMPTZ NOT NULL,
    source_name TEXT NOT NULL,
    source_version TEXT NOT NULL DEFAULT 'unknown',
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (security_id, metric_name, trade_date, denominator_period, available_at)
);

CREATE INDEX idx_valuation_pit
    ON valuation_observation(security_id, metric_name, trade_date, available_at DESC);

CREATE TABLE supply_chain_relationship (
    relationship_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_company_id UUID NOT NULL REFERENCES company_master(company_id),
    customer_company_id UUID NOT NULL REFERENCES company_master(company_id),
    relationship_type TEXT NOT NULL,
    exposure_weight NUMERIC(10,6) CHECK (exposure_weight IS NULL OR exposure_weight BETWEEN 0 AND 1),
    confidence_score NUMERIC(8,6) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    valid_from DATE NOT NULL,
    valid_to DATE,
    available_at TIMESTAMPTZ NOT NULL,
    source_url TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (supplier_company_id <> customer_company_id),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE INDEX idx_supply_supplier_pit
    ON supply_chain_relationship(supplier_company_id, valid_from, valid_to, available_at);
CREATE INDEX idx_supply_customer_pit
    ON supply_chain_relationship(customer_company_id, valid_from, valid_to, available_at);

CREATE TABLE event_observation (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    brief_date DATE NOT NULL,
    event_date DATE NOT NULL,
    source_published_at TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    headline TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('official', 'media')),
    source_url TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL UNIQUE,
    novelty_score NUMERIC(8,6) CHECK (novelty_score IS NULL OR novelty_score BETWEEN 0 AND 1),
    sentiment_score NUMERIC(8,6) CHECK (sentiment_score IS NULL OR sentiment_score BETWEEN -1 AND 1),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_event_pit ON event_observation(event_date, source_published_at, available_at);

CREATE TABLE event_company_map (
    event_id UUID NOT NULL REFERENCES event_observation(event_id),
    company_id UUID NOT NULL REFERENCES company_master(company_id),
    impact_role TEXT NOT NULL CHECK (impact_role IN ('subject', 'beneficiary', 'adversely_affected', 'peer', 'supplier', 'customer')),
    confidence_score NUMERIC(8,6) NOT NULL DEFAULT 1 CHECK (confidence_score BETWEEN 0 AND 1),
    PRIMARY KEY (event_id, company_id, impact_role)
);

CREATE INDEX idx_event_company ON event_company_map(company_id, event_id);

CREATE TABLE research_run (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_type TEXT NOT NULL CHECK (run_type IN ('ingestion', 'feature_build', 'target_build', 'backtest')),
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    data_cutoff_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'succeeded', 'failed')),
    CHECK (completed_at IS NULL OR completed_at >= started_at)
);

CREATE TABLE feature_store (
    security_id UUID NOT NULL REFERENCES security_master(security_id),
    feature_date DATE NOT NULL,
    feature_name TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    feature_value NUMERIC(28,10),
    source_period_end DATE,
    source_max_available_at TIMESTAMPTZ NOT NULL,
    lineage_run_id UUID NOT NULL REFERENCES research_run(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (security_id, feature_date, feature_name, feature_version)
);

CREATE INDEX idx_feature_cross_section
    ON feature_store(feature_date, feature_name, feature_version, security_id);

CREATE TABLE targets (
    security_id UUID NOT NULL REFERENCES security_master(security_id),
    target_date DATE NOT NULL,
    target_version TEXT NOT NULL,
    benchmark_id UUID REFERENCES security_master(security_id),
    ret_1d NUMERIC(18,10),
    ret_5d NUMERIC(18,10),
    ret_20d NUMERIC(18,10),
    ret_60d NUMERIC(18,10),
    excess_return_20d NUMERIC(18,10),
    excess_return_60d NUMERIC(18,10),
    industry_neutral_return_20d NUMERIC(18,10),
    industry_neutral_return_60d NUMERIC(18,10),
    future_vol_20d NUMERIC(18,10),
    future_max_drawdown_20d NUMERIC(18,10),
    lineage_run_id UUID NOT NULL REFERENCES research_run(run_id),
    computed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (security_id, target_date, target_version)
);

CREATE INDEX idx_targets_date ON targets(target_date, target_version, security_id);

-- Example point-in-time selection: latest known fundamental value at a decision cutoff.
-- SELECT DISTINCT ON (company_id, metric_name, fiscal_period_end, fiscal_period_type)
--        company_id, metric_name, fiscal_period_end, fiscal_period_type, metric_value, available_at
-- FROM fundamental_observation
-- WHERE available_at <= :decision_cutoff_at
-- ORDER BY company_id, metric_name, fiscal_period_end, fiscal_period_type, available_at DESC;
