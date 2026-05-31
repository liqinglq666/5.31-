# SmartPact 智契 —— AI 合同合规审查系统

基于 Vue 3 + FastAPI 的智能合规审查系统，用于比对采购结果与正式合同的关键条款差异，识别潜在合规风险。

---

## 核心特性

- **多 Agent MoE 架构**：商务审计、法务审计、风控终审三 Agent 协同，分层裁决而非单模型包办。
- **RAPTOR + GraphRAG 双轨检索**：语义切块 → 递归摘要树 → 向量召回 → 引用追踪，解决长合同上下文衰减问题。
- **反幻觉三重防线**：Pydantic Schema 硬约束 + CoVe 自验证 + PDF 原文 bbox 溯源定位。
- **LLM 动态热切换**：管理后台实时配置多模型参数并切换激活模型，无需重启服务；内置故障自动降级。
- **PDF 视觉溯源**：差异条款直接关联原始 PDF 页面坐标，前端一键高亮框选。

---

## 技术栈

| 层级 | 技术选型 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Pinia + ECharts |
| 后端 | FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 + Alembic |
| 数据库 | PostgreSQL 15 (业务数据) + Milvus 2.4 (向量检索) |
| 文档解析 | Docling (版面语义) + PyMuPDF (空间坐标) |
| Embedding | sentence-transformers (MiniLM-L6-v2, 384维本地推理) |
| LLM | OpenAI 兼容接口，支持 Moonshot / DeepSeek / Qwen / Zhipu 等 |
| 容器化 | Docker Compose (7 服务一键编排) |
| 安全 | JWT + bcrypt + Fernet 加密 |

---

## 快速开始

### 前置要求

- Docker Engine >= 24.0
- 可用内存 >= 8 GB

### Docker Compose 启动

```bash
# 1. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入 LLM_API_KEY 等必要配置

# 2. 一键启动全部服务
docker compose up -d

# 3. 查看状态
docker compose ps
```

访问：
- 前端：`http://localhost:5173`
- API 文档：`http://localhost:8002/docs`

### 本地开发

```bash
# 启动数据层
docker compose up -d postgres redis minio milvus-standalone

# 后端
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload

# 前端
cd frontend/bank-ai
npm install
npm run dev
```

---

## 项目结构

```
.
├── backend/               # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/        # RESTful API 路由
│   │   ├── application/   # 工作流编排、任务调度
│   │   ├── domain/        # 领域层（Agent、合同实体、解析器）
│   │   ├── infrastructure/# 基础设施（LLM 客户端、向量库、文档解析）
│   │   ├── models/        # SQLAlchemy ORM 模型
│   │   └── services/      # 业务服务
│   ├── alembic/           # 数据库迁移
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/bank-ai/      # Vue 3 前端
│   ├── src/
│   │   ├── api/           # Axios 封装
│   │   ├── components/    # 业务组件
│   │   ├── store/         # Pinia 状态管理
│   │   ├── types/         # TypeScript 类型
│   │   └── views/         # 页面视图
│   └── package.json
├── deploy/                # 部署脚本
└── docker-compose.yml     # 7 服务编排
```

---

## 环境变量

### 后端 `.env`

```env
POSTGRES_URL=postgresql://postgres:123456@localhost:5432/bank-ai
REDIS_URL=redis://localhost:6379/0

LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.moonshot.cn/v1
LLM_MODEL=moonshot-v1-32k

# 动态配置加密盐
DB_ENCRYPTION_KEY=your_fernet_key

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# 安全
SECRET_KEY=change-in-production
ACCESS_TOKEN_EXPIRE_HOURS=24
```

### 前端 `.env`

```env
VITE_API_BASE_URL=http://127.0.0.1:8002
```

---

## 未来方向

1. **消息队列化**：引入 Celery + RabbitMQ，支撑全行级并发审查。
2. **智能模型路由**：基于延迟、成本、准确率动态选择最优模型。
3. **GPU 加速**：启用 CUDA Execution Provider，Docling 解析速度提升 5~10 倍。
4. **端侧部署**：引入 Qwen2.5-7B / Phi-4 等小模型，格式检查等简单任务本地运行。

---

## 许可与声明

本项目为**学习交流与技术分享**而开源，代码按现状（AS-IS）提供。

> **郑重声明**：AI 生成的审查结论仅供参考，不构成任何法律或合规建议，最终决策应由具备资质的专业人员作出。

---

如需深入了解架构设计与搭建细节，可以邮件2863846826@qq.com。
