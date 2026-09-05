# Daily update operation

The platform uses different update frequencies because the source data do not change at the same speed.

| Task | Frequency | Contents |
|---|---|---|
| AI events | Every day | Official RSS/Atom discovery, time filtering, materiality threshold and URL deduplication |
| Market + QQQ | Trading days | Full price history refreshed through the latest available close |
| SEC + earnings | Trading days | Poll for new filings and reported/estimated earnings observations |
| OpenRouter usage + Cloudflare Radar | Every day | Model-token history refresh and AI product-domain ranking snapshots |
| GitHub, Hugging Face, OpenRouter | Sunday | Developer adoption and model-market snapshots |
| Research pipeline | After daily inputs | Normalize, features, targets, hypothesis tests, QA and web export |

## Safe test

```bash
python3 scripts/daily_update.py --dry-run
```

## Live update

```bash
python3 scripts/daily_update.py
```

The updater keeps `data/processed/daily_update_state.json`, writes a run report, and uses a lock so two updates cannot overlap. A failed source is recorded and is not marked successful.

## macOS scheduling

To run every day at 08:00 local time:

```bash
zsh scripts/install_macos_schedule.sh
```

The computer must be awake and connected. Logs are written to `logs/`. For an always-on production deployment, move the same command to a hosted scheduler and configure API keys as encrypted secrets.
