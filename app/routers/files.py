from fastapi import APIRouter, HTTPException, Query
from pathlib import Path

router = APIRouter(prefix="/api/file", tags=["files"])

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
ALLOWED_FILES = {"license": "license.txt", "os": "os.txt"}


@router.get("/{name}")
def read_file(name: str, max_length: int | None = Query(default=None, ge=100, le=200000)):
    if name not in ALLOWED_FILES:
        raise HTTPException(status_code=404, detail="file not found")
    path = DOCS_DIR / ALLOWED_FILES[name]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file missing")
    full = path.read_text(encoding="utf-8")
    total_size = path.stat().st_size
    truncated = False
    content = full
    if max_length is not None and len(full) > max_length:
        content = full[:max_length]
        truncated = True
    return {
        "id": name,
        "name": ALLOWED_FILES[name],
        "content": content,
        "size": total_size,
        "truncated": truncated,
        "total_chars": len(full),
    }
