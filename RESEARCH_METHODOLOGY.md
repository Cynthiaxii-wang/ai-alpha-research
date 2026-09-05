# Pilot Research Methodology v1

## Signal and target timing

- Daily market features become available after the relevant close.
- The default target enters at the next trading-day close.
- A 20D target exits 20 trading sessions after the entry close.
- Excess return subtracts the QQQ return over the identical entry/exit dates.
- Each target row records when its longest currently populated horizon became observable.

## Earnings timing

- Pre-market reports map to the same trading day when it exists.
- Post-market or unknown-time reports map to the next trading day.
- Alpha Vantage historical estimated EPS and surprise fields are explicitly marked `vendor_historical_estimate_snapshot_unverified`.

## SEC fundamentals

- Raw observations preserve XBRL tag, accession number, start/end dates, filing date, form, and fiscal period.
- Annual analysis selects the earliest filed 10-K or 20-F value across approved US-GAAP/IFRS tags for each metric and period end.
- Operating-feature availability uses the latest filing date among revenue, operating cash flow and capex; valuation availability additionally requires diluted shares.
- TSM IFRS/TWD fundamentals are used for same-currency growth and margin analysis but excluded from the USD ADR valuation proxy.
- FCF is calculated as operating cash flow minus capital expenditure.
- Total capex is not labeled as AI capex.
- Historical valuation uses unadjusted daily close divided by revenue or FCF per diluted share from the latest then-available annual filing. Return targets use split-adjusted price returns; they are not labeled dividend total returns.
- Revenue, FCF, and diluted shares are taken from the same filing-period basis. `price_to_fcf_filing_basis` is omitted when FCF is non-positive.
- This free-data valuation is a research proxy, not a vendor-grade point-in-time market-cap series; differing split/restatement conventions remain a documented limitation.

## AI-native data

- GitHub and Hugging Face values observed on 2026-09-02 are current snapshots only.
- Counts are never forward-filled backward into historical samples.
- Cross-company Hugging Face aggregates use at most the top 50 returned models by downloads.
- PLTR has no verified Hugging Face author mapping and is marked not applicable.
- Dated GitHub commits and releases are collected for one transparent repository proxy per mapped company.
- The repository is the highest-starred eligible project among the owner's 50 most recently updated repositories; this is company open-source activity, not a pure AI-adoption measure.
- Commit histories capped at 1,000 observations are explicitly marked incomplete and must not be compared as uncensored counts.
- The analyst-maintained `AI跟踪体系20260831.xlsx` snapshot contributes GPU rental prices, memory prices, quarterly CSP capex, product activity and token-usage observations.
- Imported workbook history is conservatively assigned the workbook snapshot timestamp as `available_at` unless an original publication timestamp is independently verified; otherwise it remains descriptive-only until dated historical vintages are collected.
- Missing vendor, unit or exact publication-time metadata is retained as an explicit quality flag instead of being inferred.
- Model ARR, token-price history, CDS, financing narratives and NVDA consensus fields remain excluded from the automated research layer pending stronger provenance or licensing review.

## Interpretation

The five-company pilot validates engineering and screens research hypotheses. It does not provide enough breadth, history, or independent observations for claims of robust alpha. All reported correlations are descriptive until expanded-universe, subperiod, turnover, transaction-cost, and stability tests are complete.
