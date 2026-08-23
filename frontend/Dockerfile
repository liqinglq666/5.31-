# frontend/Dockerfile
# ------------------
# 多阶段构建：
# 阶段一使用 node:20-alpine 构建 Vue3 项目；
# 阶段二使用 nginx:alpine 托管构建产物 dist 目录。

# ========================= 构建阶段 =========================
FROM node:20-alpine AS builder

WORKDIR /app

# 复制 package.json 和 lock 文件（如果有）并安装依赖
COPY bank-ai/package*.json ./
RUN npm install

# 复制前端完整源码并执行构建
COPY bank-ai/ ./
RUN npm run build

# ========================= 运行阶段 =========================
FROM nginx:alpine

# 将构建产物复制到 nginx 默认 html 目录
COPY --from=builder /app/dist /usr/share/nginx/html

# 暴露 80 端口
EXPOSE 80

# 启动 nginx（前台运行，保持容器存活）
CMD ["nginx", "-g", "daemon off;"]
