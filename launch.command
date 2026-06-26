#!/usr/bin/env bash
# Cogan Lab RP Coding Toolbox - double-click launcher (macOS Finder; also works on Linux).
# Runs the GUI in the 'rpcoding' conda env.
cd "$(dirname "$0")" || exit 1
if ! command -v conda >/dev/null 2>&1; then
  echo "conda was not found on PATH."
  echo "Activate the 'rpcoding' env and run:  rpcoding-gui"
  read -r -p "Press Enter to close… " _
  exit 1
fi
exec conda run --no-capture-output -n rpcoding python -m rpcoding.gui.app
