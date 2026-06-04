import json
from typing import Generator

from app.config import settings
from app.langfuse_compat import get_openai_client

client = get_openai_client(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)


def _build_messages(message: str, system_prompt: str | None = None) -> list[dict]:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": message})
    return messages


def chat(
    message: str,
    model: str | None = None,
    system_prompt: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    top_p: float = 1.0,
) -> dict:
    kwargs = dict(
        model=model or settings.openai_model,
        messages=_build_messages(message, system_prompt),
        temperature=temperature,
        top_p=top_p,
        name="chat-completion",
        metadata={"langfuse_tags": ["chat"]},
    )
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0]
    return {
        "content": choice.message.content,
        "model": response.model,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        },
    }


def chat_stream(
    message: str,
    model: str | None = None,
    system_prompt: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    top_p: float = 1.0,
) -> Generator[str, None, None]:
    _model = model or settings.openai_model
    kwargs = dict(
        model=_model,
        messages=_build_messages(message, system_prompt),
        temperature=temperature,
        top_p=top_p,
        stream=True,
        stream_options={"include_usage": True},
        name="chat-completion",
        metadata={"langfuse_tags": ["chat"]},
    )
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    # Enable thinking mode for models that support it (qwen3.5 etc.)
    extra_body = kwargs.get("extra_body", {})
    extra_body["enable_thinking"] = True
    kwargs["extra_body"] = extra_body

    full_text = ""
    reasoning_text = ""
    thinking_ended = False
    stream = client.chat.completions.create(**kwargs)
    for chunk in stream:
        data = {}
        if chunk.choices:
            delta = chunk.choices[0].delta
            # Detect reasoning_content via multiple access patterns
            reasoning = None
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                reasoning = delta.reasoning_content
            elif hasattr(delta, "model_extra") and delta.model_extra:
                reasoning = delta.model_extra.get("reasoning_content")
            if reasoning:
                reasoning_text += reasoning
                data["thinking"] = reasoning
            # Detect content
            if delta.content:
                if reasoning_text and not thinking_ended:
                    thinking_ended = True
                    yield f"data: {json.dumps({'thinking_done': True}, ensure_ascii=False)}\n\n"
                full_text += delta.content
                data["content"] = delta.content
            # If chunk has no content and no reasoning, it's a thinking-phase heartbeat
            elif not reasoning and reasoning_text and not thinking_ended:
                data["thinking_heartbeat"] = True
            elif not reasoning and not delta.content and not reasoning_text and not full_text:
                data["thinking_heartbeat"] = True
        if hasattr(chunk, "usage") and chunk.usage:
            data["usage"] = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }
            data["model"] = getattr(chunk, "model", "")
        if data:
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    if reasoning_text and not thinking_ended:
        yield f"data: {json.dumps({'thinking_done': True}, ensure_ascii=False)}\n\n"

    # Generate follow-up questions
    suggestions = _generate_suggestions(message, full_text, _model, temperature)
    if suggestions:
        yield f"data: {json.dumps({'suggestions': suggestions}, ensure_ascii=False)}\n\n"

    yield "data: [DONE]\n\n"


def _generate_suggestions(question: str, answer: str, model: str, temperature: float) -> list[str]:
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Based on the user's question and the AI's answer, generate exactly 3 concise follow-up questions "
                        "the user might want to ask next. Return ONLY a JSON array of strings, no other text. "
                        "Example: [\"question1\", \"question2\", \"question3\"]"
                    ),
                },
                {
                    "role": "user",
                    "content": f"Q: {question}\n\nA: {answer[:1000]}",
                },
            ],
            temperature=max(temperature, 0.8),
            max_tokens=200,
            extra_body={"enable_thinking": False},
        )
        raw = resp.choices[0].message.content.strip()
        # Extract JSON array from response
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except Exception:
        pass
    return []
