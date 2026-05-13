#!/bin/bash
# ═══════════════════════════════════════════════════════
#  每日AI前沿 - Linux 服务器部署脚本
#  用法: bash deploy.sh
#
#  前提条件:
#    1. 服务器已安装 Python 3（大多数 Linux 自带）
#    2. 你有权限在目标目录写入文件
# ═══════════════════════════════════════════════════════

set -e

APP_DIR="/opt/ai-news"
SERVICE_NAME="ai-news"

echo "═══════════════════════════════════════════"
echo "  每日AI前沿 - 服务器部署"
echo "═══════════════════════════════════════════"
echo ""

# 1. 检查 Python
echo "[1/5] 检查 Python..."
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "  [错误] 未找到 Python，请先安装 Python 3"
    exit 1
fi
echo "  Python: $($PYTHON --version)"

# 2. 创建目录
echo "[2/5] 创建应用目录: $APP_DIR"
sudo mkdir -p "$APP_DIR"

# 3. 复制文件（脚本所在目录的上级文件）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[3/5] 复制文件..."
sudo cp "$SCRIPT_DIR/serve.py" "$APP_DIR/"
sudo cp "$SCRIPT_DIR/index.html" "$APP_DIR/"
# 如果有历史数据库，也复制过去
if [ -f "$SCRIPT_DIR/ai_news.db" ]; then
    sudo cp "$SCRIPT_DIR/ai_news.db" "$APP_DIR/"
    echo "  已复制历史数据库"
fi
echo "  文件复制完成"

# 4. 数据库会由 serve.py 自动创建
echo "[4/5] 数据库将在首次启动时自动创建"

# 5. 启动服务
echo "[5/5] 启动服务..."
echo ""

# 尝试用 nohup 后台启动
sudo nohup $PYTHON "$APP_DIR/serve.py" > "$APP_DIR/server.log" 2>&1 &
SERVER_PID=$!
echo $SERVER_PID | sudo tee "$APP_DIR/server.pid" > /dev/null

sleep 2

# 检查是否启动成功
if sudo kill -0 $SERVER_PID 2>/dev/null; then
    # 获取服务器 IP
    SERVER_IP=$(hostname -I | awk '{print $1}')
    echo "═══════════════════════════════════════════"
    echo "  部署成功！"
    echo "═══════════════════════════════════════════"
    echo ""
    echo "  访问地址: http://$SERVER_IP:8899"
    echo "  进程 PID: $SERVER_PID"
    echo "  日志文件: $APP_DIR/server.log"
    echo ""
    echo "  常用命令:"
    echo "    查看状态:  sudo kill -0 $SERVER_PID && echo '运行中' || echo '已停止'"
    echo "    停止服务:  sudo kill $SERVER_PID"
    echo "    查看日志:  tail -f $APP_DIR/server.log"
    echo "    重启服务:  sudo kill $SERVER_PID && sudo nohup $PYTHON $APP_DIR/serve.py > $APP_DIR/server.log 2>&1 &"
    echo ""
    echo "═══════════════════════════════════════════"
else
    echo "  [错误] 服务启动失败，请检查日志:"
    echo "  sudo cat $APP_DIR/server.log"
    exit 1
fi
