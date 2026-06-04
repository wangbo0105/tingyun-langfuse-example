import json
from typing import Generator

from app.config import settings
from app.langfuse_compat import get_langfuse, get_openai_client

langfuse = get_langfuse()
client = get_openai_client(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)

_STEP_NAMES = {
    "intent-recognition": "意图识别",
    "knowledge-retrieval": "知识检索",
    "final-answer": "最终回答",
}

INTENT_SYSTEM = "分析用户的问题，完成以下任务：\n1. 判断问题所属领域（如：证券金融、科技互联网、汽车出行、时政新闻、编程技术、其他）\n2. 识别提问类型（如：方案设计、原因分析、对比评估、趋势预测、策略建议）\n3. 提炼核心诉求，用一句话概括用户最想知道什么\n请按以上结构简洁作答。"
RETRIEVAL_SYSTEM = "根据用户的问题，生成3条相关的背景知识或事实信息，帮助回答该问题。请简洁作答。"
ANSWER_SYSTEM = "根据提供的背景知识，回答用户的问题。请做到准确、简洁、有帮助。"


def agent_run(query: str, model: str | None = None, temperature: float = 0.7, top_p: float = 1.0) -> dict:
    _model = model or settings.openai_model

    with langfuse.start_as_current_observation(
        as_type="agent",
        name="agent-workflow",
        input={"query": query},
        metadata={"langfuse_tags": ["agent"]},
    ) as root_span:
        # Step 1: intent recognition
        with langfuse.start_as_current_observation(
            as_type="generation",
            name="intent-recognition",
            model=_model,
            input={"query": query},
        ) as intent_span:
            intent_response = client.chat.completions.create(
                model=_model,
                messages=[
                    {"role": "system", "content": INTENT_SYSTEM},
                    {"role": "user", "content": query},
                ],
                temperature=temperature,
                top_p=top_p,
            )
            intent_result = intent_response.choices[0].message.content
            intent_span.update(output={"intent": intent_result})

        # Step 2: knowledge retrieval
        with langfuse.start_as_current_observation(
            as_type="chain",
            name="knowledge-retrieval",
            input={"intent": intent_result},
        ) as retrieval_span:
            retrieval_response = client.chat.completions.create(
                model=_model,
                messages=[
                    {"role": "system", "content": RETRIEVAL_SYSTEM},
                    {"role": "user", "content": query},
                ],
                temperature=temperature,
                top_p=top_p,
            )
            retrieved_facts = retrieval_response.choices[0].message.content
            retrieval_span.update(output={"facts": retrieved_facts})

        # Step 3: generate final answer
        with langfuse.start_as_current_observation(
            as_type="generation",
            name="final-answer",
            model=_model,
            input={"query": query, "facts": retrieved_facts},
        ) as answer_span:
            final_response = client.chat.completions.create(
                model=_model,
                messages=[
                    {"role": "system", "content": ANSWER_SYSTEM},
                    {"role": "user", "content": f"问题：{query}\n\n背景知识：\n{retrieved_facts}"},
                ],
                temperature=temperature,
                top_p=top_p,
            )
            final_answer = final_response.choices[0].message.content
            answer_span.update(output={"answer": final_answer})

        root_span.update(output={"answer": final_answer})

    langfuse.flush()
    return {
        "steps": [
            {"name": "intent-recognition", "result": intent_result},
            {"name": "knowledge-retrieval", "result": retrieved_facts},
            {"name": "final-answer", "result": final_answer},
        ],
        "final_answer": final_answer,
    }


def agent_stream(
    query: str,
    model: str | None = None,
    temperature: float = 0.7,
    top_p: float = 1.0,
) -> Generator[str, None, None]:
    _model = model or settings.openai_model
    steps = []

    with langfuse.start_as_current_observation(
        as_type="agent",
        name="agent-workflow",
        input={"query": query},
        metadata={"langfuse_tags": ["agent"]},
    ) as root_span:
        # Step 1: intent recognition
        yield f"data: {json.dumps({'step_start': 'intent-recognition'}, ensure_ascii=False)}\n\n"
        with langfuse.start_as_current_observation(
            as_type="generation",
            name="intent-recognition",
            model=_model,
            input={"query": query},
        ) as intent_span:
            intent_response = client.chat.completions.create(
                model=_model,
                messages=[
                    {"role": "system", "content": INTENT_SYSTEM},
                    {"role": "user", "content": query},
                ],
                temperature=temperature,
                top_p=top_p,
            )
            intent_result = intent_response.choices[0].message.content
            intent_span.update(output={"intent": intent_result})
        steps.append({"name": "intent-recognition", "result": intent_result})
        yield f"data: {json.dumps({'step': {'name': 'intent-recognition', 'result': intent_result}}, ensure_ascii=False)}\n\n"

        # Step 2: knowledge retrieval
        yield f"data: {json.dumps({'step_start': 'knowledge-retrieval'}, ensure_ascii=False)}\n\n"
        with langfuse.start_as_current_observation(
            as_type="chain",
            name="knowledge-retrieval",
            input={"intent": intent_result},
        ) as retrieval_span:
            retrieval_response = client.chat.completions.create(
                model=_model,
                messages=[
                    {"role": "system", "content": RETRIEVAL_SYSTEM},
                    {"role": "user", "content": query},
                ],
                temperature=temperature,
                top_p=top_p,
            )
            retrieved_facts = retrieval_response.choices[0].message.content
            retrieval_span.update(output={"facts": retrieved_facts})
        steps.append({"name": "knowledge-retrieval", "result": retrieved_facts})
        yield f"data: {json.dumps({'step': {'name': 'knowledge-retrieval', 'result': retrieved_facts}}, ensure_ascii=False)}\n\n"

        # Step 3: generate final answer
        yield f"data: {json.dumps({'step_start': 'final-answer'}, ensure_ascii=False)}\n\n"
        with langfuse.start_as_current_observation(
            as_type="generation",
            name="final-answer",
            model=_model,
            input={"query": query, "facts": retrieved_facts},
        ) as answer_span:
            final_response = client.chat.completions.create(
                model=_model,
                messages=[
                    {"role": "system", "content": ANSWER_SYSTEM},
                    {"role": "user", "content": f"问题：{query}\n\n背景知识：\n{retrieved_facts}"},
                ],
                temperature=temperature,
                top_p=top_p,
            )
            final_answer = final_response.choices[0].message.content
            answer_span.update(output={"answer": final_answer})
        steps.append({"name": "final-answer", "result": final_answer})
        yield f"data: {json.dumps({'step': {'name': 'final-answer', 'result': final_answer}}, ensure_ascii=False)}\n\n"

        root_span.update(output={"answer": final_answer})

    langfuse.flush()
    yield f"data: {json.dumps({'final_answer': final_answer, 'steps': steps}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
