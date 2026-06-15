#!/bin/bash
cd "$(cd "$(dirname "$0")" && pwd)" || exit 1
python3 dev.py stop
