#!/bin/bash
# 阿里云控制台一键部署脚本
# 直接在阿里云网页终端执行

set -e

echo "========== SmartPact 部署脚本 =========="

# 1. 安装依赖
echo "[1/7] 安装系统依赖..."
apt update && apt upgrade -y
apt install -y git nginx postgresql postgresql-contrib redis-server
apt install -y python3.11 python3.11-venv python3-pip

# 安装 Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# 2. 配置数据库
echo "[2/7] 配置 PostgreSQL..."
sudo -u postgres psql <<EOF
CREATE DATABASE smartpact;
CREATE USER smartpact_user WITH PASSWORD 'SmartPact@2024';
GRANT ALL PRIVILEGES ON DATABASE smartpact TO smartpact_user;
\q
EOF

# 3. 获取代码
echo "[3/7] 下载项目代码..."
cd /opt
if [ -d "smartpact" ]; then
    echo "目录已存在，更新代码..."
    cd smartpact && git pull || echo "Git pull 失败，使用现有代码"
else
    # 方式1：如果有 GitHub 仓库，取消下面注释并修改地址
    # git clone https://github.com/yourusername/smartpact.git

    # 方式2：手动上传代码到 /opt/smartpact（推荐）
    echo "请手动上传代码到 /opt/smartpact 目录"
    echo "上传方式："
    echo "  1. 使用阿里云文件管理上传压缩包"
    echo "  2. 或使用 sz/rz 命令传输"
    exit 1
fi

# 4. 后端配置
echo "[4/7] 配置后端..."
cd /opt/smartpact/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 创建 .env 文件
if [ ! -f ".env" ]; then
cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql+asyncpg://smartpact_user:SmartPact@2024@localhost:5432/smartpact

# JWT
SECRET_KEY=your-super-secret-jwt-key-change-this
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Moonshot AI - 请替换为你的真实 API Key
MOONSHOT_API_KEY=sk-your-moonshot-api-key-here
MOONSHOT_BASE_URL=https://api.moonshot.cn/v1
MOONSHOT_MODEL=moonshot-v1-32k

# File Upload
MAX_FILE_SIZE=52428800
UPLOAD_DIR=uploads

# Environment
ENVIRONMENT=production
LOG_LEVEL=INFO
EOF
    echo "警告：请编辑 /opt/smartpact/backend/.env 文件，填入正确的 MOONSHOT_API_KEY"
fi

# 初始化数据库
alembic upgrade head

# 5. 前端构建
echo "[5/7] 构建前端..."
cd /opt/smartpact/frontend/bank-ai
npm install
npm run build
mkdir -p /var/www/smartpact_frontend
cp -r dist/* /var/www/smartpact_frontend/
chown -R www-data:www-data /var/www/smartpact_frontend

# 6. Nginx 配置
echo "[6/7] 配置 Nginx..."
cp /opt/smartpact/deploy/smartpact.conf /etc/nginx/conf.d/
nginx -t && systemctl reload nginx
systemctl enable nginx

# 7. 创建后端服务
echo "[7/7] 配置后端服务..."
cat > /etc/systemd/system/smartpact.service << 'EOF'
[Unit]
Description=SmartPact Backend API
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/smartpact/backend
Environment=PATH=/opt/smartpact/backend/venv/bin
ExecStart=/opt/smartpact/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable smartpact

echo ""
echo "========== 部署完成 =========="
echo ""
echo "请完成以下步骤："
echo "1. 编辑 /opt/smartpact/backend/.env，填入正确的 MOONSHOT_API_KEY"
echo "2. 启动后端：systemctl start smartpact"
echo "3. 检查状态：systemctl status smartpact"
echo "4. 访问：http://8.163.95.238"
echo ""
