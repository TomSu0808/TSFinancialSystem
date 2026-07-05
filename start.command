#!/bin/bash
cd "$(cd "$(dirname "$0")" && pwd)" || exit 1
./start.sh
echo
echo "Start command has finished. Keep the service terminal windows open if they are still running."
echo "Press any key to close this window..."
read -n 1 -s
