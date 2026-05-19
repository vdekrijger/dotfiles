#!/usr/bin/env bash
set -euo pipefail

# Install a weekly launchd schedule for pattern-eval.
# Generates a plist from your current environment and loads it.
#
# Usage:
#   bash ~/.claude/skills/pattern-eval/install-schedule.sh [OPTIONS]
#
# Options:
#   --day       Weekday (0=Sun, 1=Mon, ..., 5=Fri, 6=Sat). Default: 1 (Monday)
#   --hour      Hour (0-23). Default: 9
#   --minute    Minute (0-59). Default: 0
#   --project   Working directory for Claude. Default: current directory
#   --uninstall Remove the schedule

LABEL="com.claude.pattern-eval"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

# Defaults
DAY=1
HOUR=9
MINUTE=0
PROJECT_DIR="$(pwd)"
UNINSTALL=false

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --day)      DAY="$2"; shift 2 ;;
    --hour)     HOUR="$2"; shift 2 ;;
    --minute)   MINUTE="$2"; shift 2 ;;
    --project)  PROJECT_DIR="$2"; shift 2 ;;
    --uninstall) UNINSTALL=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# Uninstall
if [ "$UNINSTALL" = true ]; then
  if launchctl list "$LABEL" &>/dev/null; then
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  fi
  rm -f "$PLIST"
  echo "Uninstalled $LABEL"
  exit 0
fi

# Find claude binary
CLAUDE_BIN="$(command -v claude 2>/dev/null || echo "$HOME/.local/bin/claude")"
if [ ! -x "$CLAUDE_BIN" ]; then
  echo "Error: claude not found at $CLAUDE_BIN"
  echo "Install Claude Code first: https://docs.anthropic.com/en/docs/claude-code"
  exit 1
fi

# Validate project dir
if [ ! -d "$PROJECT_DIR" ]; then
  echo "Error: project directory does not exist: $PROJECT_DIR"
  exit 1
fi

DAY_NAMES=("Sunday" "Monday" "Tuesday" "Wednesday" "Thursday" "Friday" "Saturday")

echo "Installing pattern-eval schedule:"
echo "  When: ${DAY_NAMES[$DAY]} at $(printf '%02d:%02d' "$HOUR" "$MINUTE")"
echo "  Project: $PROJECT_DIR"
echo "  Claude: $CLAUDE_BIN"
echo "  Plist: $PLIST"
echo ""

# Unload existing if present
if launchctl list "$LABEL" &>/dev/null; then
  launchctl unload "$PLIST" 2>/dev/null || true
  echo "  Unloaded existing schedule"
fi

# Write plist
cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${CLAUDE_BIN}</string>
    <string>-p</string>
    <string>/pattern-eval</string>
    <string>--permission-mode</string>
    <string>auto</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${PROJECT_DIR}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>${DAY}</integer>
    <key>Hour</key>
    <integer>${HOUR}</integer>
    <key>Minute</key>
    <integer>${MINUTE}</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/tmp/claude-pattern-eval.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/claude-pattern-eval.err</string>
</dict>
</plist>
EOF

# Load it
launchctl load "$PLIST"

echo ""
echo "Done. Schedule is active."
echo ""
echo "Note: launchd does NOT wake your Mac from sleep."
echo "If your laptop is asleep at the scheduled time, the job is skipped."
echo ""
echo "Useful commands:"
echo "  Check status:  launchctl list $LABEL"
echo "  View output:   cat /tmp/claude-pattern-eval.log"
echo "  View errors:   cat /tmp/claude-pattern-eval.err"
echo "  Uninstall:     bash $0 --uninstall"
