# Langfuse 接入听云 Python 探针 — 技术方案

## 1. 概述

### 1.1 背景

[Langfuse](https://langfuse.com/) 是一个开源的 LLM 可观测性平台，为 AI 应用提供 Tracing、Prompt Management 和 Evaluation 能力。Langfuse 通过 OpenTelemetry Span 管理观测生命周期，用户通过 `start_as_current_observation` / `update` / `end` 等 API 记录 LLM 调用链路。

### 1.2 目标

将 Langfuse 的观测数据桥接到听云 Python 探针（`tingyun-agent-python`），实现：

- **零侵入**：用户无需修改任何 Langfuse 代码，探针自动捕获 observation 生命周期
- **类型适配**：根据 Langfuse observation 类型（generation / agent / tool / span 等）映射到听云对应的追踪节点
- **数据完整**：从 `_otel_span.attributes` 提取 model、output、token 用量等最终化数据
- **链路关联**：将 Langfuse 的 `trace_id` / `span_id` 写入 invocation attributes，便于与 Langfuse 平台联动

### 1.3 适用版本

| 依赖 | 版本 |
|------|------|
| `langfuse` | ≥ 3.0.0（OTEL-based 架构） |
| `tingyun-agent-python` | ≥ 4.2.0.0 |
| Python | 3.7 ~ 3.14 |

---

## 2. Langfuse 架构分析

### 2.1 类继承体系

```
Langfuse (client)
├── start_as_current_observation()  → _AgnosticContextManager  # 根级 observation
├── start_observation()             → Observation 对象         # 根级，非 context manager
└── _create_span_with_parent_context()

LangfuseObservationWrapper (base, langfuse._client.span)
├── __init__(otel_span, as_type, input, output, model, ...)
├── end()                              # 结束 observation
├── update(output=..., usage_details=...)  # 更新数据（可多次调用）
├── start_as_current_observation()     → _AgnosticContextManager  # 子 observation
└── start_observation()                → Observation 对象

LangfuseSpan(LangfuseObservationWrapper)         # as_type="span"
LangfuseGeneration(LangfuseObservationWrapper)   # as_type="generation"
LangfuseAgent(LangfuseObservationWrapper)        # as_type="agent"
LangfuseTool(LangfuseObservationWrapper)         # as_type="tool"
LangfuseChain(LangfuseObservationWrapper)        # as_type="chain"
LangfuseRetriever(LangfuseObservationWrapper)    # as_type="retriever"
LangfuseEmbedding(LangfuseObservationWrapper)    # as_type="embedding"
LangfuseEvaluator(LangfuseObservationWrapper)    # as_type="evaluator"
LangfuseGuardrail(LangfuseObservationWrapper)    # as_type="guardrail"
```

### 2.2 数据流时序

```
                    Langfuse SDK                                听云探针
                    ──────────                                 ────────
1. __init__(as_type="generation", model="gpt-4", input=...)
   │                                              →  创建 InvokeLLMTrace，__enter__
   │                                                 提取 input, model
   │
2. update(output="response", usage_details={...})
   │  (可多次调用)
   │  数据写入 _otel_span.attributes
   │
3. end()
   │  _otel_span.end()                            →  从 _otel_span.attributes 提取:
   │                                                 output, usage_details, model
   │                                              →  stop_invoke()
   ▼
```

### 2.3 `_otel_span.attributes` 关键 Key

| Langfuse Attribute Key | 类型 | 说明 |
|------------------------|------|------|
| `langfuse.observation.type` | `str` | observation 类型 (generation/span/agent/...) |
| `langfuse.observation.input` | `str` (JSON) | 输入数据 |
| `langfuse.observation.output` | `str` (JSON) | 输出数据（含 update 后的数据） |
| `langfuse.observation.model.name` | `str` | 模型名称 |
| `langfuse.observation.usage_details` | `str` (JSON) | Token 用量 |
| `langfuse.observation.model.parameters` | `str` (JSON) | 模型参数 |

`usage_details` JSON 结构（示例）：

```json
{"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
```

### 2.4 `_otel_span.context` 结构

```
_Span(
    name="OpenAI-generation",
    context=SpanContext(
        trace_id=0x70cac475801af7260d67e7fdb8ce7d81,  # int, 128-bit
        span_id=0x274ceff3ad63b32b,                     # int, 64-bit
        trace_flags=0x03,
        ...
    )
)
```

---

## 3. 技术方案

### 3.1 插装策略

**核心思路**：拦截 `LangfuseObservationWrapper` 基类的 `__init__` 和 `end()` 方法，所有子类自动生效。

| 拦截点 | 时机 | 行为 |
|--------|------|------|
| `LangfuseObservationWrapper.__init__` | observation 创建 | 创建听云追踪节点，提取 input、model，`__enter__` |
| `LangfuseObservationWrapper.end()` | observation 结束 | 先调原始 `end()`，从 `_otel_span.attributes` 提取 output/token，`stop_invoke()` |

### 3.2 Observation 类型映射

| Langfuse `as_type` | 听云 Tracker | Invocation | 提取的数据 |
|---------------------|-------------|------------|-----------|
| `generation` | `InvokeLLMTrace` | `LLMInvocation` | model, input, output, usage_details, model_parameters |
| `embedding` | `InvokeLLMTrace` | `LLMInvocation` | model, input, output, usage_details |
| `agent` | `InvokeAgentTrace` | `InvokeAgentInvocation` | input, output |
| `tool` | `InvokeToolTrace` | `ExecuteToolInvocation` | input→tool_call_arguments, output→tool_call_result |
| `span` | `FunctionTracker` | — | — |
| `chain` | `FunctionTracker` | — | — |
| `retriever` | `FunctionTracker` | — | — |
| `evaluator` | `FunctionTracker` | — | — |
| `guardrail` | `FunctionTracker` | — | — |

### 3.3 数据提取时序

```
┌──────────────────────────────────────────────────────────────┐
│                    __init__ 阶段                              │
│                                                              │
│  kwargs.input     ──→  invocation.input_messages             │
│  kwargs.model     ──→  invocation.request_model              │
│                                                              │
│  trace_node.__enter__()                                      │
│  setattr(instance, "_ty_trace_node", trace_node)             │
└──────────────────────────────────────────────────────────────┘
                          │
                     用户业务逻辑
                     (可能调用 update)
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│                    end() 阶段                                 │
│                                                              │
│  1. wrapped(*args, **kwargs)   # 原始 end()，确保属性完整    │
│                                                              │
│  2. _otel_span.context        ──→  langfuse_trace_id         │
│                               ──→  langfuse_span_id          │
│                                                              │
│  3. _otel_span.attributes:                                   │
│     output                   ──→  invocation.output_messages  │
│     usage_details            ──→  input/output/total_tokens  │
│     model.name               ──→  invocation.request_model   │
│     model.parameters         ──→  temperature, top_p, ...    │
│                                                              │
│  4. trace_node.stop_invoke()                                 │
│  5. delattr(instance, "_ty_trace_node")                      │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. 文件结构

### 4.1 新增/修改文件

```
tingyun/
├── armoury/
│   ├── langfuse/
│   │   └── __init__.py          # [新增] Observation 插装核心逻辑
│   └── adapter_langfuse.py      # [已有] HTTP 上报数据拦截（Langfuse v2 batch 方式）
└── embattle/
    └── repertoire.py            # [修改] 注册 import hook
```

### 4.2 注册配置

```python
# tingyun/embattle/repertoire.py
"langfuse": [
    {
        # 已有：拦截 HTTP 上报（v2 batch 方式）
        "target": "langfuse.request",
        "hook_func": "instrument_langfuse_client",
        "hook_module": "tingyun.armoury.adapter_langfuse",
    },
    {
        # 新增：拦截 observation 生命周期（v3 OTEL 方式）
        "target": "langfuse._client.span",
        "hook_func": "instrument_span_observation",
        "hook_module": "tingyun.armoury.langfuse",
    },
],
```

### 4.3 模块依赖

```
tingyun.armoury.langfuse
├── tingyun.armoury.ammunition.function_tracker.FunctionTracker
├── tingyun.armoury.ammunition.llm_tracker.InvokeLLMTrace
├── tingyun.armoury.ammunition.llm_tracker.InvokeAgentTrace
├── tingyun.armoury.ammunition.llm_tracker.InvokeToolTrace
├── tingyun.armoury.ammunition.tracker.current_tracker
├── tingyun.packages.wrapt.wrap_function_wrapper
└── tingyun.utils.genai.types.{LLMInvocation, InvokeAgentInvocation, ExecuteToolInvocation}
```

---

## 5. 核心实现

### 5.1 `__init__` 拦截 — 创建追踪节点

```python
def wrap_observation_init(wrapped, instance, args, kwargs):
    # 1. 先调原始 __init__
    wrapped(*args, **kwargs)

    # 2. 获取当前 tracker
    tracker = current_tracker()
    if not tracker:
        return

    # 3. 从 kwargs 提取 as_type，从 otel_span 提取 name
    as_type = kwargs.get("as_type")
    name = getattr(instance._otel_span, "name", "") or as_type

    # 4. 根据 as_type 创建对应的追踪节点
    trace_node = _create_trace_node(tracker, name, as_type, kwargs)
    trace_node.__enter__()

    # 5. 存储到 instance 上，供 end() 时使用
    setattr(instance, "_ty_trace_node", trace_node)
```

### 5.2 `end()` 拦截 — 提取最终数据

```python
def wrap_observation_end(wrapped, instance, args, kwargs):
    # 1. 先调原始 end()，确保 _otel_span 属性完整
    result = wrapped(*args, **kwargs)

    trace_node = getattr(instance, "_ty_trace_node", None)
    if trace_node is None:
        return result

    # 2. 从 _otel_span 提取最终数据
    _apply_finalized_attributes(instance, trace_node)

    # 3. 关闭追踪节点
    trace_node.stop_invoke()

    # 4. 清理引用
    delattr(instance, "_ty_trace_node")
    return result
```

### 5.3 数据提取 — 从 `_otel_span.attributes` 读取

```python
def _apply_otel_attributes_to_llm(otel_attrs, trace_node):
    invocation = trace_node.invocation

    # output
    output_raw = otel_attrs.get("langfuse.observation.output")
    if output_raw:
        invocation.output_messages = [_serialize_value(output_raw)]

    # usage_details (JSON string → dict)
    usage_raw = otel_attrs.get("langfuse.observation.usage_details")
    if usage_raw:
        usage = json.loads(usage_raw)  # {"prompt_tokens": 100, "completion_tokens": 50, ...}
        invocation.input_tokens = usage.get("prompt_tokens")
        invocation.output_tokens = usage.get("completion_tokens")
        invocation.total_tokens = usage.get("total_tokens")

    # model
    model = otel_attrs.get("langfuse.observation.model.name")
    if model:
        invocation.request_model = model
```

### 5.4 Langfuse ID 关联

```python
def _apply_langfuse_ids(otel_span, invocation):
    ctx = otel_span.context
    invocation.attributes["langfuse_trace_id"] = format(ctx.trace_id, "032x")
    invocation.attributes["langfuse_span_id"] = format(ctx.span_id, "016x")
```

写入结果示例：

```python
invocation.attributes = {
    "langfuse_trace_id": "70cac475801af7260d67e7fdb8ce7d81",
    "langfuse_span_id": "274ceff3ad63b32b",
}
```

---

## 6. 上报数据字段映射

### 6.1 LLM 类型 (generation / embedding)

| 听云属性 (`gen_ai.*`) | 来源 |
|-----------------------|------|
| `gen_ai.request.model` | `kwargs.model` / `_otel_span.attributes["langfuse.observation.model.name"]` |
| `gen_ai.provider.name` | 固定值 `"langfuse"` |
| `gen_ai.framework` | 固定值 `"langfuse"` |
| `gen_ai.operation.name` | 默认 `"chat"` |
| `gen_ai.usage.input_tokens` | `usage_details["prompt_tokens"]` |
| `gen_ai.usage.output_tokens` | `usage_details["completion_tokens"]` |
| `gen_ai.usage.total_tokens` | `usage_details["total_tokens"]` |
| `gen_ai.request.temperature` | `model_parameters["temperature"]` |
| `gen_ai.request.top_p` | `model_parameters["top_p"]` |
| `gen_ai.request.max_tokens` | `model_parameters["max_tokens"]` |
| `langfuse_trace_id` | `otel_span.context.trace_id` (hex) |
| `langfuse_span_id` | `otel_span.context.span_id` (hex) |

### 6.2 Agent 类型

| 听云属性 | 来源 |
|---------|------|
| `gen_ai.provider.name` | 固定值 `"langfuse"` |
| `gen_ai.framework` | 固定值 `"langfuse"` |
| `langfuse_trace_id` | `otel_span.context.trace_id` (hex) |
| `langfuse_span_id` | `otel_span.context.span_id` (hex) |

### 6.3 Tool 类型

| 听云属性 | 来源 |
|---------|------|
| `gen_ai.provider.name` | 固定值 `"langfuse"` |
| `gen_ai.framework` | 固定值 `"langfuse"` |
| `langfuse_trace_id` | `otel_span.context.trace_id` (hex) |
| `langfuse_span_id` | `otel_span.context.span_id` (hex) |

---

## 7. 用户使用示例

### 7.1 用户代码（无需任何修改）

```python
from langfuse import Langfuse

langfuse = Langfuse()

# 根级 span
with langfuse.start_as_current_observation(name="chat-agent", as_type="agent") as agent_span:

    # LLM generation
    with agent_span.start_as_current_observation(
        name="openai-call",
        as_type="generation",
        model="gpt-4o",
        input={"messages": [{"role": "user", "content": "Hello"}]}
    ) as gen_span:
        response = openai_client.chat.completions.create(...)
        gen_span.update(
            output=response.choices[0].message.content,
            usage_details={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        )

    # Tool call
    with agent_span.start_as_current_observation(name="web-search", as_type="tool") as tool_span:
        results = search(query)
        tool_span.update(output=results)
```

### 7.2 探针自动生成的追踪树

```
BackgroundTask (chat-agent)
├── InvokeAgentTrace (chat-agent)              # as_type="agent"
│   ├── InvokeLLMTrace (openai-call)           # as_type="generation"
│   │   ├── request_model: "gpt-4o"
│   │   ├── input_tokens: 100
│   │   ├── output_tokens: 50
│   │   ├── langfuse_trace_id: "70cac..."
│   │   └── langfuse_span_id: "274ce..."
│   └── InvokeToolTrace (web-search)           # as_type="tool"
│       ├── tool_call_arguments: "{query}"
│       ├── tool_call_result: "{results}"
│       ├── langfuse_trace_id: "70cac..."
│       └── langfuse_span_id: "a1b2c3..."
```

---

## 8. 两种插装方式对比

探针当前包含 **两套** Langfuse 插装，面向不同使用场景：

| 维度 | 方式一：HTTP 上报拦截 | 方式二：Observation 生命周期拦截 |
|------|----------------------|-------------------------------|
| **文件** | `tingyun/armoury/adapter_langfuse.py` | `tingyun/armoury/langfuse/__init__.py` |
| **拦截点** | `LangfuseClient.post` | `LangfuseObservationWrapper.__init__` / `end()` |
| **触发时机** | Langfuse 批量上报时（异步） | observation 创建/结束时（同步） |
| **数据来源** | 解析 HTTP batch JSON | 从 `_otel_span.attributes` 读取 |
| **时间精度** | 使用事件中的预设时间戳 | 使用实时时间戳 |
| **上下文** | 创建独立 BackgroundTask | 嵌入当前请求的追踪树 |
| **适用场景** | 无探针上下文的离线回放 | 有探针上下文的在线实时追踪 |

**推荐组合使用**：方式二优先（在线实时、有上下文），方式一作为兜底（离线数据回放）。

---

## 9. 异常处理与防御

| 场景 | 处理方式 |
|------|---------|
| 无 `current_tracker()` | 直接透传，不创建追踪节点 |
| `__init__` 中创建追踪节点失败 | catch 异常，`_logger.debug`，不影响 Langfuse 正常运行 |
| `end()` 中提取属性失败 | catch 异常，仍尝试 `stop_invoke()` |
| `end()` 中 `stop_invoke()` 失败 | catch 异常，清理 `_ty_trace_node` 引用 |
| observation 未调 `end()`（如异常退出） | 追踪节点不会被关闭（与 Langfuse 行为一致） |
| `otel_span.attributes` 为空或不存在 | 跳过属性提取，仅记录 Langfuse ID |

**核心原则**：任何听云插装异常都不应影响 Langfuse 的正常功能。

---

## 10. 测试验证要点

### 10.1 功能测试

- [ ] `generation` 类型：验证 model、input/output、token 用量正确上报
- [ ] `embedding` 类型：验证 model、token 用量正确上报
- [ ] `agent` 类型：验证 input/output 正确上报
- [ ] `tool` 类型：验证 tool_call_arguments / tool_call_result 正确上报
- [ ] `span` / `chain` 等通用类型：验证 FunctionTracker 正确创建
- [ ] 嵌套 observation：验证父子层级正确
- [ ] `update()` 后调 `end()`：验证最终数据包含 update 内容

### 10.2 异常测试

- [ ] 探针未启动时：Langfuse 功能完全不受影响
- [ ] `gen_ai.enabled = false`：不创建追踪节点
- [ ] `end()` 抛异常：追踪节点仍能正确清理

### 10.3 集成测试

- [ ] 与 OpenAI 插装共存：Langfuse generation 内包含 OpenAI 调用，形成嵌套追踪树
- [ ] Langfuse `langfuse_trace_id` 与听云 trace 正确关联
- [ ] 多线程/异步场景下追踪节点不串
