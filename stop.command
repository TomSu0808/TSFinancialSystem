#!/bin/bash
cd "$(cd "$(dirname "$0")" && pwd)" || exit 1
./stop.sh
echo
echo "Stop command has finished."
echo "Press any key to close this window..."
read -n 1 -s
