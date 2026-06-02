from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api/config", tags=["config"])

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

# Fields to expose (display_name, env_key, is_secret)
CONFIG_FIELDS = [
    ("OpenAI API Key", "OPENAI_API_KEY", True, "text"),
    ("OpenAI Base URL", "OPENAI_BASE_URL", False, "text"),
    ("默认模型", "OPENAI_MODEL", False, "text"),
    ("Chat/Agent/Chain 模型列表", "OPENAI_MODELS", False, "tags"),
    ("Embedding API Key", "EMBEDDING_API_KEY", True, "text"),
    ("Embedding Base URL", "EMBEDDING_BASE_URL", False, "text"),
    ("Embedding 默认模型", "EMBEDDING_MODEL", False, "text"),
    ("Embedding 模型列表", "EMBEDDING_MODELS", False, "tags"),
    ("Langfuse Public Key", "LANGFUSE_PUBLIC_KEY", True, "text"),
    ("Langfuse Secret Key", "LANGFUSE_SECRET_KEY", True, "text"),
    ("Langfuse Host", "LANGFUSE_HOST", False, "text"),
]


def _read_env() -> dict[str, str]:
    data = {}
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
    return data


def _write_env(data: dict[str, str]) -> None:
    # Preserve original order and comments
    existing = _read_env()
    existing.update(data)
    lines = []
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                lines.append(line)
                continue
            if "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k in data:
                    lines.append(f"{k}={data[k]}")
                    existing.pop(k, None)
                else:
                    lines.append(line)
        # Add any new keys
        for k, v in existing.items():
            if k in data:
                lines.append(f"{k}={v}")
    else:
        for k, v in data.items():
            lines.append(f"{k}={v}")
    _ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _reload_settings() -> None:
    import importlib
    import app.config as mod
    importlib.reload(mod)
    # Update the module-level `settings` object used by other modules
    from app.config import settings as new_settings
    mod.settings = new_settings


class ConfigResponse(BaseModel):
    fields: list[dict]


class ConfigUpdateRequest(BaseModel):
    values: dict[str, str]


@router.get("", response_model=ConfigResponse)
def get_config():
    env = _read_env()
    fields = []
    for label, key, secret, input_type in CONFIG_FIELDS:
        val = env.get(key, getattr(settings, key.lower(), ""))
        fields.append({"label": label, "key": key, "value": val, "secret": secret, "type": input_type})
    return ConfigResponse(fields=fields)


@router.put("")
def update_config(req: ConfigUpdateRequest):
    _write_env(req.values)
    _reload_settings()
    # Also update the live client instances
    _update_live_clients()
    return {"ok": True}


def _update_live_clients():
    try:
        from app.config import settings as s
        import app.services.chat_service as cs
        cs.client.api_key = s.openai_api_key
        cs.client.base_url = s.openai_base_url

        import app.services.agent_service as ag
        ag.client.api_key = s.openai_api_key
        ag.client.base_url = s.openai_base_url

        import app.services.tools_service as ts
        ts.client.api_key = s.openai_api_key
        ts.client.base_url = s.openai_base_url

        import app.services.embedding_service as es
        es.client.api_key = s.embedding_api_key
        es.client.base_url = s.embedding_base_url

        import langfuse
        langfuse.Langfuse(public_key=s.langfuse_public_key, secret_key=s.langfuse_secret_key, host=s.langfuse_host)
    except Exception:
        pass
