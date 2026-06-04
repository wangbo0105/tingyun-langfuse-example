# TingYun OpenAI Example

基于 OpenAI Python SDK 的 LLM 应用可观测性演示项目。通过四个典型场景展示如何使用听云探针对 LLM 调用链路进行全链路追踪、监控和分析。

## 场景介绍

| 场景            | 观测类型               | 说明                                  |
|---------------|--------------------|-------------------------------------|
| **Chat**      | Generation         | 基础对话，支持流式输出与深度思考（reasoning_content） |
| **Agent**     | Agent > Generation | 多步推理：意图识别 → 知识检索 → 最终回答             |
| **Chain**     | Chain + Tool       | 函数调用链路：天气查询、数学计算、时区查询、汇率换算          |
| **Embedding** | Generation         | 文本向量化，对比不同文本的语义相似度                  |

## 功能特性

- **实时流式输出** — Chat 和 Agent 场景支持 SSE 流式响应，逐步展示输出过程
- **深度思考展示** — 自动识别模型的 reasoning_content，区分展示思考过程与正文回答
- **Agent 多步推理** — 拆解意图、检索知识、组织回答，三步可视化
- **Tool 函数调用** — 天气/计算/时区/汇率四种工具，模型自主决策调用
- **模型热切换** — 支持运行时切换模型，无需重启服务
- **环境配置面板** — 左侧配置按钮可在线修改 `.env`，实时生效
- **中断控制** — 输出过程中可随时中断，切换场景自动取消进行中的请求
- **追问建议** — 每次回答后自动生成 3 条追问建议，一键继续对话

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repo-url>
cd tingyun-langfuse-example

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

复制示例配置文件并填入实际的 API Key：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# Chat (OpenAI 兼容接口)
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-plus
OPENAI_MODELS=qwen3.5-plus,qwen-max,qwen-plus,qwen-turbo,qwen-long,qwen-vl-max

# Embedding
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_MODELS=text-embedding-v1,text-embedding-v2,text-embedding-v3,text-embedding-v4
```

> 也可以启动后在页面左下角「环境配置」面板中在线修改，保存后实时生效。

### 3. 启动服务

```bash
python run.py
```

访问 [http://localhost:8002](http://localhost:8002) 即可使用。

## 项目结构

```
tingyun-langfuse-example/
├── app/
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py             # 配置管理（pydantic-settings）
│   ├── static/
│   │   └── index.html        # 前端页面（单文件 SPA）
│   ├── routers/
│   │   ├── chat.py           # Chat 接口（同步 + 流式）
│   │   ├── agent.py          # Agent 接口（同步 + 流式）
│   │   ├── tools.py          # Chain + Tool 接口
│   │   ├── embedding.py      # Embedding 接口
│   │   ├── config.py         # 环境配置读写接口
│   │   └── files.py          # 文件读取接口
│   └── services/
│       ├── chat_service.py   # Chat 业务逻辑
│       ├── agent_service.py  # Agent 三步推理
│       ├── tools_service.py  # Tool 定义与执行
│       └── embedding_service.py  # Embedding 向量化
├── .env.example              # 环境变量模板
├── requirements.txt          # Python 依赖
├── run.py                    # 启动脚本
└── README.md
```

## API 接口

| 方法   | 路径                  | 说明                   |
|------|---------------------|----------------------|
| POST | `/api/chat`         | Chat 同步对话            |
| POST | `/api/chat/stream`  | Chat 流式对话（SSE）       |
| POST | `/api/agent`        | Agent 同步执行           |
| POST | `/api/agent/stream` | Agent 流式执行（SSE）      |
| POST | `/api/tools`        | Chain + Tool 函数调用    |
| POST | `/api/embedding`    | 文本向量化                |
| GET  | `/api/config`       | 获取环境配置               |
| PUT  | `/api/config`       | 更新环境配置（写入 .env 并热重载） |

## 技术栈

- **后端**: FastAPI + Uvicorn
- **LLM SDK**: OpenAI Python SDK
- **前端**: Tailwind CSS + Vanilla JS（单 HTML 文件）
- **配置**: pydantic-settings + python-dotenv
