# 阿里云轻量服务器部署指南

## 服务器信息
- **公网 IP**: 8.163.95.238
- **操作系统**: Ubuntu 22.04 LTS (推荐)
- **配置**: 2核4G 或以上

---

## 第一步：连接服务器

```bash
ssh root@8.163.95.238
```

---

## 第二步：安装系统依赖

```bash
# 更新系统
apt update && apt upgrade -y

# 安装基础工具
apt install -y git nginx postgresql postgresql-contrib redis-server

# 安装 Node.js 20.x (前端构建需要)
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# 安装 Python 3.11 和 pip
apt install -y python3.11 python3.11-venv python3-pip

# 验证安装
node -v    # v20.x.x
npm -v     # 10.x.x
python3 --version  # 3.11.x
```

---

## 第三步：配置 PostgreSQL

```bash
# 切换到 postgres 用户
sudo -u postgres psql

# 在 psql 中执行
CREATE DATABASE smartpact;
CREATE USER smartpact_user WITH PASSWORD 'your_strong_password';
GRANT ALL PRIVILEGES ON DATABASE smartpact TO smartpact_user;
\q
```

---

## 第四步：上传项目代码

### 方式1：使用 scp 上传（推荐）

在本地终端执行：

```bash
# 进入项目目录
cd d:\bank-ai-system

# 压缩项目（排除 node_modules 和 venv）
tar -czvf smartpact.tar.gz --exclude='frontend/bank-ai/node_modules' --exclude='frontend/bank-ai/dist' --exclude='__pycache__' --exclude='*.pyc' --exclude='.git' backend/ frontend/ deploy/ docker-compose.yml README.md

# 上传到服务器
scp smartpact.tar.gz root@8.163.95.238:/opt/

# SSH 到服务器解压
ssh root@8.163.95.238 "cd /opt && tar -xzvf smartpact.tar.gz && mv bank-ai-system smartpact"
```

### 方式2：使用 git 克隆（如果代码已推送到仓库）

```bash
cd /opt
git clone <your-repo-url> smartpact
cd smartpact
```

---

## 第五步：配置后端

```bash
cd /opt/smartpact/backend

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 创建 .env 配置文件
cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql+asyncpg://smartpact_user:your_strong_password@localhost:5432/smartpact

# JWT
SECRET_KEY=your-super-secret-jwt-key-change-this-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Moonshot AI
MOONSHOT_API_KEY=sk-your-moonshot-api-key
MOONSHOT_BASE_URL=https://api.moonshot.cn/v1
MOONSHOT_MODEL=moonshot-v1-32k

# File Upload
MAX_FILE_SIZE=52428800
UPLOAD_DIR=uploads

# Environment
ENVIRONMENT=production
LOG_LEVEL=INFO
EOF

# 初始化数据库
alembic upgrade head
```

---

## 第六步：配置前端

```bash
cd /opt/smartpact/frontend/bank-ai

# 安装依赖
npm install

# 构建生产版本
npm run build

# 移动构建产物到 Nginx 目录
mkdir -p /var/www/smartpact_frontend
cp -r dist/* /var/www/smartpact_frontend/

# 设置权限
chown -R www-data:www-data /var/www/smartpact_frontend
```

---

## 第七步：配置 Nginx

```bash
# 复制配置文件
cp /opt/smartpact/deploy/smartpact.conf /etc/nginx/conf.d/

# 测试配置
nginx -t

# 重载 Nginx
systemctl reload nginx

# 设置开机自启
systemctl enable nginx
```

---

## 第八步：配置 Systemd 服务（后端）

```bash
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

# 重载 systemd
systemctl daemon-reload

# 启动服务
systemctl start smartpact
systemctl enable smartpact

# 查看状态
systemctl status smartpact
```

---

## 第九步：配置防火墙

```bash
# 安装 ufw
apt install -y ufw

# 允许 HTTP/HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# 允许 SSH（重要！先允许再启用）
ufw allow 22/tcp

# 启用防火墙
ufw enable

# 查看状态
ufw status
```

---

## 第十步：验证部署

```bash
# 测试后端健康检查
curl http://8.163.95.238/health

# 测试 API
curl http://8.163.95.238/api/v1/stats

# 查看后端日志
journalctl -u smartpact -f

# 查看 Nginx 日志
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

---

## 访问系统

- **前端**: http://8.163.95.238
- **API 文档**: http://8.163.95.238/api/docs (Swagger UI)
- **健康检查**: http://8.163.95.238/health

---

## 常用运维命令

```bash
# 重启后端
systemctl restart smartpact

# 查看后端日志
journalctl -u smartpact -f

# 重启 Nginx
systemctl reload nginx

# 更新前端（重新构建后）
cd /opt/smartpact/frontend/bank-ai
git pull  # 如果有更新
npm install
npm run build
cp -r dist/* /var/www/smartpact_frontend/

# 更新后端
cd /opt/smartpact/backend
git pull
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
systemctl restart smartpact
```

---

## 可选：配置 HTTPS (SSL)

```bash
# 安装 certbot
apt install -y certbot python3-certbot-nginx

# 申请证书（按提示操作）
certbot --nginx -d your-domain.com

# 自动续期测试
certbot renew --dry-run
```

---

## 故障排查

### 后端无法启动
```bash
# 检查日志
journalctl -u smartpact -n 100

# 手动测试
source /opt/smartpact/backend/venv/bin/activate
cd /opt/smartpact/backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 前端 404
```bash
# 检查 Nginx 配置
cat /etc/nginx/conf.d/smartpact.conf

# 检查文件是否存在
ls -la /var/www/smartpact_frontend/
```

### 数据库连接失败
```bash
# 检查 PostgreSQL 状态
systemctl status postgresql

# 检查连接
sudo -u postgres psql -c "\l"
```
