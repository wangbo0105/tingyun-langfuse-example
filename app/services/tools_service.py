import json
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

from app.config import settings
from app.langfuse_compat import get_langfuse, get_openai_client

langfuse = get_langfuse()
client = get_openai_client(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)

CURRENCY_RATES_TO_CNY = {
    "CNY": 1.0,
    "USD": 7.20,
    "EUR": 7.85,
    "JPY": 0.048,
    "GBP": 9.15,
    "HKD": 0.92,
    "KRW": 0.0053,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "当用户询问某个城市的天气、温度、气候等信息时，必须调用此工具来获取实时天气数据。不要自己编造天气信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "城市名称，如北京、东京、纽约",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "温度单位，默认摄氏度",
                    },
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "当用户要求计算数学表达式或进行数值运算时，必须调用此工具来获取精确结果。不要自己计算。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 (15 * 28 + 120) / 6",
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "当用户询问某个地方现在几点、当前时间、当地时间等问题时，必须调用此工具来获取准确的实时时间。不要自己猜测时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "IANA 时区标识，如 Asia/Shanghai（北京）、Asia/Tokyo（东京）、Europe/London（伦敦）、America/New_York（纽约）",
                    },
                },
                "required": ["timezone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_currency",
            "description": "当用户询问货币兑换、汇率换算等问题时，必须调用此工具来进行精确换算。支持 CNY、USD、EUR、JPY、GBP、HKD、KRW 之间的互换。",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "要换算的金额",
                    },
                    "from_currency": {
                        "type": "string",
                        "description": "源货币代码，如 USD、EUR、JPY、CNY",
                    },
                    "to_currency": {
                        "type": "string",
                        "description": "目标货币代码，如 USD、EUR、JPY、CNY",
                    },
                },
                "required": ["amount", "from_currency", "to_currency"],
            },
        },
    },
]


def _execute_tool(name: str, args: dict) -> str:
    if name == "get_weather":
        return json.dumps({
            "location": args["location"],
            "temperature": "22",
            "unit": args.get("unit", "celsius"),
            "condition": "sunny",
            "humidity": "45%",
        })
    if name == "calculate":
        try:
            result = eval(args["expression"], {"__builtins__": {}}, {})
            return json.dumps({"result": str(result)})
        except Exception as e:
            return json.dumps({"error": f"invalid expression: {e}"})
    if name == "get_current_time":
        tz_name = args.get("timezone", "UTC")
        try:
            tz = ZoneInfo(tz_name) if ZoneInfo else None
            now = datetime.now(tz) if tz else datetime.utcnow()
            return json.dumps({
                "timezone": tz_name,
                "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
                "weekday": now.strftime("%A"),
            })
        except Exception as e:
            return json.dumps({"error": f"invalid timezone: {e}"})
    if name == "convert_currency":
        amount = float(args["amount"])
        src = str(args["from_currency"]).upper()
        dst = str(args["to_currency"]).upper()
        src_rate = CURRENCY_RATES_TO_CNY.get(src)
        dst_rate = CURRENCY_RATES_TO_CNY.get(dst)
        if src_rate is None or dst_rate is None:
            supported = ", ".join(sorted(CURRENCY_RATES_TO_CNY.keys()))
            return json.dumps({"error": f"unsupported currency. supported: {supported}"})
        cny_value = amount * src_rate
        converted = cny_value / dst_rate
        return json.dumps({
            "amount": amount,
            "from": src,
            "to": dst,
            "rate": round(src_rate / dst_rate, 6),
            "result": round(converted, 2),
        })
    return json.dumps({"error": f"unknown tool: {name}"})


def tools_run(query: str, model: str | None = None, temperature: float = 0.7, top_p: float = 1.0) -> dict:
    _model = model or settings.openai_model

    with langfuse.start_as_current_observation(
        as_type="chain",
        name="tool-calling-workflow",
        input={"query": query},
        metadata={"langfuse_tags": ["tools"]},
    ) as root_span:
        messages = [{"role": "user", "content": query}]

        first_response = client.chat.completions.create(
            model=_model,
            messages=messages,
            tools=TOOLS,
            temperature=temperature,
            top_p=top_p,
            name="tool-decision",
        )

        choice = first_response.choices[0]
        tool_results = []

        if choice.finish_reason == "tool_calls":
            messages.append(choice.message)

            for tool_call in choice.message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)

                with langfuse.start_as_current_observation(
                    as_type="tool",
                    name=f"tool-{fn_name}",
                    input={"arguments": fn_args},
                ) as tool_span:
                    result = _execute_tool(fn_name, fn_args)
                    tool_span.update(output={"result": json.loads(result)})

                tool_results.append({
                    "tool": fn_name,
                    "arguments": fn_args,
                    "result": json.loads(result),
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

            final_response = client.chat.completions.create(
                model=_model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                name="tool-summary",
            )
            final_answer = final_response.choices[0].message.content
        else:
            final_answer = choice.message.content

        root_span.update(output={"answer": final_answer})

    langfuse.flush()
    return {
        "tool_calls": tool_results,
        "final_answer": final_answer,
    }
