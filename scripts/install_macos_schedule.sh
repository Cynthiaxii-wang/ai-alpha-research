#!/bin/zsh
set -eu
PROJECT_DIR="${0:A:h:h}"
LABEL="com.ai-alpha-research.daily-update"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs"
/usr/bin/python3 - "$PROJECT_DIR" "$PLIST" <<'PY'
import plistlib, sys
from pathlib import Path
project, output = Path(sys.argv[1]), Path(sys.argv[2])
payload = {
    "Label": "com.ai-alpha-research.daily-update",
    "ProgramArguments": ["/usr/bin/python3", str(project / "scripts" / "daily_update.py")],
    "WorkingDirectory": str(project),
    "StartCalendarInterval": {"Hour": 8, "Minute": 0},
    "RunAtLoad": False,
    "EnvironmentVariables": {
        "HOME": str(Path.home()),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "GIT_TERMINAL_PROMPT": "0",
    },
    "StandardOutPath": str(project / "logs" / "daily_update.log"),
    "StandardErrorPath": str(project / "logs" / "daily_update.error.log"),
}
output.write_bytes(plistlib.dumps(payload))
PY
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed: daily at 08:00 Asia/Shanghai -> $PLIST"
