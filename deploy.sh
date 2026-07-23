#!/bin/bash
# ============================================================
# 微信公众号深度研究工具 - 腾讯云一键部署脚本
# 前置条件：代码已通过 git clone 放到 /opt/wechat-insight
# 使用方法：
#   cd /opt/wechat-insight
#   sudo bash deploy.sh
# ============================================================
set -e

APP_DIR="/opt/wechat-insight"
PORT=5000

echo ""
echo "============================================"
echo "  微信公众号深度研究工具 - 腾讯云部署"
echo "============================================"
echo ""

# 检查是否为 root
if [ "$EUID" -ne 0 ]; then
  echo "❌ 请用 root 用户执行: sudo bash deploy.sh"
  exit 1
fi

# 检查是否在正确的目录
if [ "$(pwd)" != "$APP_DIR" ]; then
  echo "❌ 请在 $APP_DIR 目录下运行此脚本"
  echo "   例如: cd $APP_DIR && sudo bash deploy.sh"
  exit 1
fi

# 1. 更新系统
echo "[1/7] 更新系统包..."
apt update -y && apt upgrade -y

# 2. 安装系统依赖
echo "[2/7] 安装 Python、Supervisor..."
apt install -y python3 python3-venv python3-pip git supervisor curl

# 3. 确认代码已就位
echo "[3/7] 确认代码目录..."
if [ ! -f "$APP_DIR/app.py" ]; then
  echo "❌ 未找到 app.py，请确认代码已克隆到 $APP_DIR"
  exit 1
fi

# 4. 创建 Python 虚拟环境
echo "[4/7] 创建 Python 虚拟环境..."
python3 -m venv "$APP_DIR/venv"

# 5. 安装 Python 依赖
echo "[5/7] 安装 Python 依赖..."
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# 6. 配置 Supervisor 进程守护
echo "[6/7] 配置进程守护（Supervisor）..."
cat > /etc/supervisor/conf.d/wechat-insight.conf << EOF
[program:wechat-insight]
command=$APP_DIR/venv/bin/gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 600
directory=$APP_DIR
autostart=true
autorestart=true
startsecs=3
stderr_logfile=/var/log/wechat-insight.err.log
stdout_logfile=/var/log/wechat-insight.out.log
environment=PYTHONUNBUFFERED="1"
EOF

supervisorctl reread
supervisorctl update
supervisorctl restart wechat-insight 2>/dev/null || supervisorctl start wechat-insight

# 7. 配置防火墙
echo "[7/7] 配置防火墙..."
ufw allow ${PORT}/tcp 2>/dev/null || true

# 获取公网 IP
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s ip.sb 2>/dev/null || hostname -I | awk '{print $1}')

echo ""
echo "============================================"
echo "  ✅ 部署完成！"
echo "============================================"
echo ""
echo "  访问地址: http://${PUBLIC_IP}:${PORT}"
echo ""
echo "  ⚠️  如果无法访问，请检查："
echo "     1. 腾讯云控制台 → 防火墙 → 添加规则："
echo "        协议 TCP，端口 ${PORT}，来源 0.0.0.0/0"
echo "     2. 服务状态: supervisorctl status wechat-insight"
echo "     3. 运行日志: tail -f /var/log/wechat-insight.out.log"
echo ""
echo "  常用命令："
echo "    重启: supervisorctl restart wechat-insight"
echo "    停止: supervisorctl stop wechat-insight"
echo "    状态: supervisorctl status"
echo "    日志: tail -f /var/log/wechat-insight.out.log"
echo "    更新: cd $APP_DIR && git pull && supervisorctl restart wechat-insight"
echo ""
echo "  代理配置（可选，降低反爬风险）："
echo "    编辑 $APP_DIR/proxies.txt，每行一个代理地址"
echo "    或设置环境变量 PROXY_LIST=http://ip:port,http://ip2:port"
echo ""
