#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    for script in ("normalize_data.py", "build_features_targets.py", "validate_research.py", "build_warehouse.py", "run_hypotheses.py", "build_warehouse.py", "export_web_data.py"):
        print(f"==> {script}", flush=True)
        subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / script)], cwd=PROJECT_ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
