#!/bin/bash
cd "$(cd "$(dirname "$0")" && pwd)" || exit 1
./start.sh
echo
echo "启动命令已结束。若服务仍在运行，请保持相关终端窗口打开。"
echo "按任意键关闭此窗口..."
read -n 1 -s
