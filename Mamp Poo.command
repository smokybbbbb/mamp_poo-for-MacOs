#!/bin/bash
# Mamp Poo launcher — double-click to run.
# Closes its Terminal window after starting the app.

cd "$(dirname "$0")"

# Pick the first available python3
PYTHON=$(command -v python3 || command -v python)

if [ -z "$PYTHON" ]; then
    osascript -e 'display dialog "Python 3 not found. Install from https://www.python.org/downloads/ first." buttons {"OK"} default button "OK" with icon stop with title "Mamp Poo"'
    exit 1
fi

# Launch detached so the Terminal can close
nohup "$PYTHON" main.py >/dev/null 2>&1 &
disown

# Close the Terminal window that opened this script
osascript -e 'tell application "Terminal" to close (every window whose name contains "Mamp Poo.command")' &>/dev/null
exit 0
