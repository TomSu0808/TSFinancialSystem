#!/bin/bash
cd "$(cd "$(dirname "$0")" && pwd)" || exit 1
./stop.sh
echo
echo "关闭命令已执行。"
echo "按任意键关闭此窗口..."
read -n 1 -s
