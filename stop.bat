@echo off
title Asset Manager - Stop
cd /d "%~dp0"
python dev.py stop
pause
