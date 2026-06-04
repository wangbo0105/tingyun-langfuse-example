# 听云 Python 探针 — Langfuse 集成技术文档

## 1. 概述

听云 Python 探针（v4.2.0+）内置 Langfuse 集成模块，可自动发现并采集基于 Langfuse SDK 构建的 AI 应用链路数据，包括 LLM 调用、Embedding、Agent 执行、Tool 调用和 Chain 编排等环节的性能指标与遥测数据。

**核心能力：**

- **零代码侵入**：探针自动检测 Langfuse SDK 并完成插装，无需修改业务代码
- **全链路关联**：将 Langfuse Trace 与听云 APM 事务自动关联，支持端到端链路追踪
- **GenAI 语义标准化**：将 Langfuse 的 observation 数据映射为 OpenTelemetry GenAI Semantic Conventions 标准属性
- **五种 Observation 类型全覆盖**：generation、embedding、agent、tool、chain
- **异常自动采集**：通过 OTel SpanStatus 检测错误状态，自动记录异常信息
- **重复插装防护**：Langfuse 活跃期间自动抑制 Provider 级 SDK 的重复采集

---

## 2. 前置条件

| 条件 | 说明 |
|------|------|
| Python 版本 | 3.7 ~ 3.14（含 PyPy） |
| 听云探针 | v4.2.0.0 及以上 |
| Langfuse SDK | 3.9.0 及以上（含 4.x） |
| GenAI 监控 | 探针配置中 `gen_ai.enabled` 需为 `True`（默认开启） |

---

## 3. 工作原理

### 3.1 自动发现机制

听云探针通过 Python Import Hook 机制，在应用启动时注册 Langfuse 模块的拦截规则。当应用代码首次导入 Langfuse SDK 时，探针会自动拦截 `LangfuseSpanProcessor` 的生命周期回调，完成插装：

| 拦截目标 | 作用 |
|---------|------|
| `LangfuseSpanProcessor.on_start` | 在 Observation Span 创建时，构建听云追踪节点并压入追踪栈 |
| `LangfuseSpanProcessor.on_end` | 在 Observation Span 结束时，读取完整属性与状态并写入 GenAI 语义数据 |

### 3.2 数据采集流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                        应用进程                                      │
│                                                                     │
│  用户代码                                                           │
│    │                                                                │
│    ▼                                                                │
│  Langfuse SDK                                                       │
│    │  创建 Observation Span (generation / embedding / ...)          │
│    │                                                                │
│    ▼                                                                │
│  LangfuseSpanProcessor                                              │
│    │                                                                │
│    ├── on_start() ──────► 听云探针拦截                              │
│    │                       创建 LangfuseTraceNode                   │
│    │                       压入追踪栈，记录开始时间                   │
│    │                       设置 framework 信号（抑制重复采集）        │
│    │                                                                │
│    ├── ... Span 执行中 ...                                          │
│    │                                                                │
│    └── on_end() ────────► 听云探针拦截                              │
│                            读取完整 Span Attributes                  │
│                            读取 Span Status（检测异常）              │
│                            按 observation type 构建 Invocation       │
│                            写入 GenAI 语义属性                       │
│                            关联 Langfuse Trace ID                   │
│                            重置 framework 信号                      │
│                            结束追踪节点                              │
│                                                                     │
│    │                                                                │
│    ▼                                                                │
│  听云后端 ── 数据上报                                                │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.3 重复插装防护

当 Langfuse 集成活跃时，探针会自动抑制 Provider 级 SDK（如 OpenAI、DashScope 等）的重复插装，避免同一 LLM 调用被重复采集：

- **on_start 阶段**：调用 `set_framework_llm_active()` 设置抑制信号
- **on_end 阶段**：调用 `reset_framework_llm_active()` 重置信号，恢复 Provider 级插装

### 3.4 Trace 关联

探针自动将 Langfuse 的 Trace 信息与听云事务进行关联：

- **Langfuse Trace ID**：写入追踪节点的自定义参数，格式为 32 位十六进制字符串
- **Langfuse Span ID**：写入追踪节点的自定义参数，格式为 16 位十六进制字符串；同一事务内多个 Span 以分号 `;` 拼接

通过此关联，可在听云平台直接跳转至 Langfuse 面板查看详细的 LLM 交互数据。

---

## 4. 支持的 Observation 类型

听云探针完整支持 Langfuse 的 5 种 Observation 类型，并为每种类型采集对应的性能指标与内容数据：

### 4.1 Generation（LLM 调用）

对应 Langfuse 的 `generation` 类型，即对大语言模型的调用。

**采集数据：**

| 数据类别 | 属性 | 说明 |
|---------|------|------|
| 模型信息 | `gen_ai.request.model` | 请求的模型名称（如 `gpt-4o`、`claude-3-opus`） |
| 输入内容 | `gen_ai.input.messages` | 发送给模型的输入消息（受采集开关控制） |
| 输出内容 | `gen_ai.output.messages` | 模型返回的输出消息（受采集开关控制） |
| Token 用量 | `gen_ai.usage.input_tokens` | 输入 Token 数 |
| | `gen_ai.usage.output_tokens` | 输出 Token 数 |
| | `gen_ai.usage.total_tokens` | 总 Token 数 |
| 模型参数 | `gen_ai.request.temperature` | 温度参数 |
| | `gen_ai.request.top_p` | Top-P 采样参数 |
| | `gen_ai.request.max_tokens` | 最大生成 Token 数 |
| | `gen_ai.request.frequency_penalty` | 频率惩罚 |
| | `gen_ai.request.presence_penalty` | 存在惩罚 |
| 元数据 | `gen_ai.operation.name` | 操作类型：`chat` |
| | `gen_ai.span.kind` | Span 类别：`LLM` |
| | `gen_ai.provider.name` | 固定为 `langfuse` |
| | `gen_ai.framework` | 固定为 `langfuse` |

### 4.2 Embedding（向量化调用）

对应 Langfuse 的 `embedding` 类型，即文本向量化操作。

**采集数据：**

| 数据类别 | 属性 | 说明 |
|---------|------|------|
| 模型信息 | `gen_ai.request.model` | 请求的 Embedding 模型名称 |
| Token 用量 | `gen_ai.usage.input_tokens` | 输入 Token 数 |
| | `gen_ai.usage.total_tokens` | 总 Token 数 |
| 元数据 | `gen_ai.operation.name` | 操作类型：`embeddings` |
| | `gen_ai.span.kind` | Span 类别：`EMBEDDING` |

### 4.3 Agent（智能体调用）

对应 Langfuse 的 `agent` 类型，即 AI Agent 的执行过程。

**采集数据：**

| 数据类别 | 属性 | 说明 |
|---------|------|------|
| Agent 名称 | `gen_ai.agent.name` | 从 Span 名称中提取的 Agent 名称 |
| 输入内容 | `gen_ai.input.messages` | Agent 接收的输入 |
| 输出内容 | `gen_ai.output.messages` | Agent 产生的输出 |
| 元数据 | `gen_ai.operation.name` | 操作类型：`invoke_agent` |
| | `gen_ai.span.kind` | Span 类别：`AGENT` |

### 4.4 Tool（工具调用）

对应 Langfuse 的 `tool` 类型，即 Agent 调用外部工具的过程。

**采集数据：**

| 数据类别 | 属性 | 说明 |
|---------|------|------|
| 调用参数 | `gen_ai.tool.call.arguments` | 工具调用的参数 |
| 调用结果 | `gen_ai.tool.call.result` | 工具返回的结果 |
| 元数据 | `gen_ai.operation.name` | 操作类型：`execute_tool` |
| | `gen_ai.span.kind` | Span 类别：`TOOL` |

### 4.5 Chain（链式编排）

对应 Langfuse 的 `chain` 类型，即多步骤编排流程。

**采集数据：**

| 数据类别 | 属性 | 说明 |
|---------|------|------|
| 输入内容 | `gen_ai.input.messages` | Chain 的输入数据 |
| 输出内容 | `gen_ai.output.messages` | Chain 的输出数据 |
| 元数据 | `gen_ai.operation.name` | 操作类型：`workflow` |
| | `gen_ai.span.kind` | Span 类别：`CHAIN` |

---

## 5. 异常处理

### 5.1 异常检测机制

探针通过读取 OTel Span 的 `Status` 对象检测异常状态。当 Span Status 的 `status_code` 为 `ERROR` 时，探针会自动记录异常信息：

| Span Status 字段 | 用途 | 示例 |
|-----------------|------|------|
| `status_code` | 判断是否为错误状态 | `"ERROR"` |
| `description` | 错误描述信息，写入 ExceptionNode 的 message | `"Error code: 404 - {'error': {'message': 'The model does not exist'}}` |

### 5.2 异常记录方式

当检测到错误状态时，探针会：

1. **创建 ExceptionNode**：以 `class_name="ERROR"` 和 `status.description` 作为异常消息，追加到追踪节点的异常列表中
2. **保留其他属性**：错误不会中断类型分派流程，仍然会正常采集模型名称、Token 用量等已有的属性数据

异常信息会在听云平台的调用链详情中以 `SegmentException` 形式展示。

---

## 6. 配置说明

Langfuse 集成**无需额外配置**，探针自动完成。GenAI 相关开关请在听云平台进行配置。

### 6.1 平台配置路径

登录听云平台，进入 **应用配置** → **应用设置** → **请求**，找到 **GenAI应用监控** 区域。

### 6.2 配置项说明

| 配置项 | 默认值 | 说明 |
|-------|--------|------|
| **GenAI应用监控** | 开启 | GenAI 监控总开关，关闭后不采集任何 GenAI 数据 |
| 监控流式调用 | 开启 | 是否采集流式（Streaming）调用数据 |
| 采集GenAI请求内容 | 关闭 | 是否采集 LLM 的输入内容（Prompt） |
| 请求内容长度 | `1024` | 输入内容的最大采集长度（1~3000），超出部分截断 |
| 采集GenAI响应内容 | 关闭 | 是否采集 LLM 的输出内容（Completion） |
| 响应内容长度 | `1024` | 输出内容的最大采集长度（1~3000），超出部分截断 |

> **安全提示**：`采集GenAI请求内容` 和 `采集GenAI响应内容` 默认为关闭，以避免敏感数据（如用户对话内容）被采集。如需开启，请评估数据安全合规要求。

---

## 7. 快速接入

### 7.1 安装探针

通过 OneAgent 方式安装听云探针，详细操作请参考 [听云统一探针部署文档](https://gy-demo.networkbench.com/o11y-doc/docs/doc/Agent/apm_deploy/UniAgent/auto_deploy/)。

安装完成后，编辑 `/opt/tingyun-oneagent/conf/interceptor.conf`，开启 Python Agent 采集：

```ini
python_enabled=true
```

配置完成后，**重启应用**即可自动检测 Langfuse SDK 并完成插装，无需修改任何业务代码。

### 7.2 验证

1. 登录听云平台，进入 **应用配置** → **请求** → **GenAI 应用监控**，开启相关配置
2. 触发业务中的 GenAI 调用
3. 进入 **应用与微服务** → **应用** → **应用详情** → **分布式追踪**，找到对应的追踪记录
4. 点击追踪查看详情，对比 Langfuse 采集的数据，确认模型名称、Token 用量、输入输出内容等信息一致
5. 若存在错误，异常信息会显示在调用链详情中

---

## 8. 数据属性映射

以下是 Langfuse SDK 内部 Span Attributes 与听云 GenAI 语义属性的映射关系：

| Langfuse Span Attribute | 听云语义属性 | 说明 |
|------------------------|-------------|------|
| `langfuse.observation.type` | 用于类型分派 | 决定创建哪种 Invocation 对象 |
| `langfuse.observation.input` | `gen_ai.input.messages` / `gen_ai.tool.call.arguments` | 输入数据 |
| `langfuse.observation.output` | `gen_ai.output.messages` / `gen_ai.tool.call.result` | 输出数据 |
| `langfuse.observation.model.name` | `gen_ai.request.model` | 模型名称 |
| `langfuse.observation.usage_details` | `gen_ai.usage.input_tokens` / `output_tokens` / `total_tokens` | Token 用量 |
| `langfuse.observation.model.parameters` | `gen_ai.request.temperature` / `top_p` / `max_tokens` 等 | 模型调用参数 |
| Span Status `status_code` | — | 错误状态检测（`ERROR` 时记录异常） |
| Span Status `description` | ExceptionNode.message | 错误描述信息 |

所有语义属性均遵循 [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) 标准。

---

## 9. 兼容性说明

| 项目 | 说明 |
|------|------|
| Langfuse SDK 2.x | ❌ 不支持（无 SpanProcessor 模块） |
| Langfuse SDK 3.0.0 ~ 3.8.x | ❌ 不支持（缺少 `on_start` 方法） |
| Langfuse SDK 3.9.0 ~ 3.x | ✅ 完全支持 |
| Langfuse SDK 4.x | ✅ 完全支持 |
| Langfuse Decorator 模式 | ✅ 支持（通过 SpanProcessor 拦截） |
| Langfuse 低级 API 模式 | ✅ 支持（通过 SpanProcessor 拦截） |
| Langfuse Langchain 集成 | ✅ 支持（自动抑制重复采集） |
| Langfuse OpenTelemetry 导出 | ✅ 兼容（听云读取 Span Attributes，不干扰原有 OTel 导出） |
| 异步应用（asyncio） | ✅ 支持 |

---

## 10. 性能影响

听云探针针对 Langfuse 集成进行了性能优化：

- **轻量级拦截**：仅在 Span 生命周期回调中执行轻量操作，不阻塞业务逻辑
- **线程安全**：使用细粒度锁保护共享状态（`_trace_nodes_lock`），减少竞争
- **防御性设计**：所有插装点均包含异常保护，即使探针逻辑异常也不会影响 Langfuse SDK 的正常功能
- **延迟属性填充**：在 `on_start` 阶段仅创建轻量节点，在 `on_end` 阶段才执行完整属性解析，避免不必要的开销

---

## 11. 常见问题

### Q1：需要修改 Langfuse 相关代码吗？

**不需要。** 听云探针通过自动插装实现，您的 Langfuse 代码无需任何修改。

### Q2：Langfuse 集成需要额外配置吗？

**不需要。** 只要应用中使用了 Langfuse SDK，探针会自动检测并完成集成。您可能需要根据业务需要调整 GenAI 全局配置（如是否采集输入输出内容）。

### Q3：同时使用 Langfuse 和 LangChain 时会重复采集吗？

**不会。** 探针在 Langfuse Span 活跃期间会自动设置抑制信号，阻止 Provider 级 SDK（OpenAI、DashScope 等）对同一调用的重复采集。

### Q4：输入输出内容会被采集吗？生产环境是否安全？

默认**不采集**。需在听云平台 **应用配置 → 应用设置 → 请求 → GenAI应用监控** 中手动开启「采集GenAI请求内容」和「采集GenAI响应内容」。由于可能涉及用户对话等敏感数据，请根据贵司数据安全策略评估后再决定是否开启。

### Q5：支持 Langfuse 自托管（Self-hosted）版本吗？

**支持。** 听云探针采集的是 Langfuse SDK 的 Span 数据，与 Langfuse 后端部署方式无关。

### Q6：LLM 调用出错时会记录异常信息吗？

**会。** 探针通过读取 OTel Span Status 检测错误状态。当 `status_code` 为 `ERROR` 时，会自动将错误描述（`description`）记录为异常节点，在听云平台的调用链详情中可查看完整的错误信息。

---

## 12. 技术支持

如遇问题，请联系听云技术支持，并提供以下信息：

- 听云探针版本
- Langfuse SDK 版本（`pip show langfuse`）
- Python 版本
- 相关错误日志（探针 debug 日志中搜索 `[Langfuse]` 前缀）

---

> **文档版本**：1.1 | **适用探针版本**：4.2.0.0 及以上 | **更新日期**：2026-06
