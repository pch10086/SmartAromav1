# SmartAroma

本地原型：Vue 3 + TypeScript 触屏友好界面，Python FastAPI 后端通过 **魔搭 ModelScope 推理 API**（OpenAI 兼容 SDK）或 **阿里云 DashScope** 调用千问生成香薰序列，按秒推送状态并支持暂停 / 恢复 / 终止。风扇与香型在本地以日志与进度条模拟，后续可替换 `FanBackend` 为树莓派 GPIO。

## 环境要求

- Python 3.10+
- Node.js 18+（仅开发 / 构建前端）

## 推荐目录约定

- 推荐直接使用项目内的后端虚拟环境：`backend/.venv`
- 不建议把本项目依赖统一放到外部公共目录（如 `/media/da/dym/Inclass/env`），以免与其他课程项目发生依赖冲突
- 如果仓库中已经存在 `backend/.venv`，通常可以直接复用，无需重新创建

## 最快上手（优先阅读）

如果你只是想先把项目跑起来，建议按下面顺序操作。

### 1. 启动后端

```bash
cd /media/da/dym/Inclass/inform_net/hw2/SmartAroma-main/backend
source .venv/bin/activate
PYTHONPATH=src uvicorn smart_aroma.main:app --reload --host 0.0.0.0 --port 8000
```

说明：

- 若 `backend/.venv` 已存在，可直接使用
- 若 `.env` 已存在，后端会自动读取配置
- 即使未配置 `MODELSCOPE_API_KEY` 或 `DASHSCOPE_API_KEY`，也可以使用内置 **MOCK 离线演示** 跑通基础流程

### 2. 启动前端（新终端）

```bash
cd /media/da/dym/Inclass/inform_net/hw2/SmartAroma-main/frontend
npm run dev
```

浏览器打开 Vite 提示的地址（通常为 `http://localhost:5173`）。接口与 WebSocket 会经由 Vite 代理到 `8000` 端口。

---

## 从零初始化（当本地还没有环境时）

### 1. 后端初始化

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env：优先填入 MODELSCOPE_API_KEY（魔搭 Token）；或填 DASHSCOPE_API_KEY；都不填则使用内置 MOCK 离线演示
PYTHONPATH=src uvicorn smart_aroma.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. 前端初始化

```bash
cd frontend
npm install
npm run dev
```

## 配置说明

后端支持三种运行模式：

1. **ModelScope 模式**：配置 `MODELSCOPE_API_KEY`
2. **DashScope 模式**：未配置 `MODELSCOPE_API_KEY` 时，若配置 `DASHSCOPE_API_KEY` 则使用该模式
3. **MOCK 模式**：两个 Key 都未配置时，自动进入离线演示模式

可参考 `backend/.env.example`：

```env
MODELSCOPE_API_KEY=
DASHSCOPE_API_KEY=
# FRONTEND_DIST=../frontend/dist
```

## 生产 / 树莓派单端口部署

```bash
cd frontend && npm run build
cd ../backend
export FRONTEND_DIST=../frontend/dist
PYTHONPATH=src uvicorn smart_aroma.main:app --host 0.0.0.0 --port 8000
```

浏览器访问 `http://<设备IP>:8000`。触屏场景可配合 Chromium kiosk 全屏运行。

## API 摘要

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/state` | 当前状态 JSON |
| POST | `/api/start` | body: `{"preference":"助眠"}` 等 |
| POST | `/api/pause` | 暂停 |
| POST | `/api/resume` | 恢复 |
| POST | `/api/stop` | 终止 |
| WebSocket | `/ws/status` | 约每秒推送与 `/api/state` 相同结构 |

日志默认写入 `backend/logs/smart_aroma.log`（在运行目录下创建）。

## 模块说明（后端 `src/smart_aroma`）

- `models/`：Pydantic 计划结构与校验、离线 mock 计划
- `llm/`：千问调用、提示词、从模型输出中提取 JSON
- `engine/`：`AromaController` 状态机与 `FanBackend` 占位实现（后续可替换 GPIO）
- `api/`：REST 路由；`main.py` 注册 WebSocket 与可选静态资源
