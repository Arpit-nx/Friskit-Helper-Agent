"""Load source documents and turn them into retrieval-ready chunks."""
from __future__ import annotations
import json, logging, re
from pathlib import Path
from typing import Any

log = logging.getLogger("rag.ingestion")
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def _clean(value: Any) -> str:
    if value is None: return ""
    if isinstance(value, (str, int, float, bool)): return str(value)
    if isinstance(value, list): return "\n".join(_clean(x) for x in value if _clean(x))
    if isinstance(value, dict): return "\n".join(f"{k}: {_clean(v)}" for k, v in value.items() if _clean(v))
    return ""


def _topic_to_text(topic: dict[str, Any]) -> str:

    # Preserve the source's actual fields; do not invent missing workflow details.
    parts = [f"Title: {topic.get('title', '')}", f"Topic ID: {topic.get('id', '')}"]
    for key, label in [("description", "Description"), ("keywords", "Keywords"), ("ask", "Example questions"),
                       ("find", "Navigation"), ("how", "Instructions"), ("figures", "Figures"),
                       ("qa", "Q&A"), ("operation", "Operation")]:
        if topic.get(key): parts.append(f"{label}:\n{_clean(topic[key])}")
    return "\n\n".join(p for p in parts if p.strip())


def load_documents() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    json_path = DATA_DIR / "help-catalog.json"
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError(
                    "help-catalog.json must contain a root-level array of topics"
                )

            topics = payload
            for topic in topics:
                if not isinstance(topic, dict): continue
                text = _topic_to_text(topic)
                if not text.strip():
                    continue

                navigation_steps = topic.get("find") or []

                # Preserve primary navigation instructions.
                # Alternative shortcuts are not included in the main step sequence.
                navigation_steps = [
                    step.strip()
                    for step in navigation_steps
                    if isinstance(step, str)
                    and step.strip()
                    and not step.strip().lower().startswith(
                        ("or ", "alternatively")
                    )
                ]

                docs.append({
                    "id": topic.get("id", f"friskit-{len(docs)}"),
                    "title": topic.get("title", "Untitled"),
                    "page_id": topic.get("page_id"),
                    "text": text,
                    "source": "friskit-help-catalog",
                    "source_type": "product_knowledge",
                    "route": topic.get("path") or topic.get("route"),
                    "roles": topic.get("roles", []),
                    "permission": topic.get("permission"),
                    "has_tour": topic.get(
                        "hasTour",
                        topic.get("has_tour", False)
                    ),
                    "tour_id": topic.get("tourId") or topic.get("tour_id"),
                    "navigation_steps": navigation_steps
                })
            log.info("INGEST_JSON_OK path=%s topics=%d", json_path, len(topics))
        except Exception:
            log.exception("INGEST_JSON_FAILED path=%s", json_path)
            raise
    else:
        log.warning("INGEST_JSON_MISSING path=%s", json_path)

    for path in sorted((DATA_DIR / "knowledge").glob("**/*.md")) if (DATA_DIR / "knowledge").exists() else []:
        text = path.read_text(encoding="utf-8").strip()
        if text:
            docs.append({"id": f"md:{path.relative_to(DATA_DIR).as_posix()}", "title": path.stem.replace("-", " ").title(),
                         "text": text, "source": str(path.relative_to(ROOT)), "source_type": "knowledge_document",
                         "route": None, "roles": [], "permission": None, "has_tour": False, "tour_id": None})

    for path in sorted((DATA_DIR / "examples").glob("**/*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            docs.append({"id": f"example:{path.relative_to(DATA_DIR).as_posix()}", "title": path.stem.replace("-", " ").title(),
                         "text": text, "source": str(path.relative_to(ROOT)), "source_type": "generic_example",
                         "route": None, "roles": [], "permission": None, "has_tour": False, "tour_id": None})
    log.info("INGEST_COMPLETE documents=%d", len(docs))
    return docs


def split_text(text: str, size: int, overlap: int) -> list[str]:
    # First split at headings/paragraphs; then enforce a hard character ceiling.
    units = [u.strip() for u in re.split(r"\n\s*\n", text) if u.strip()]
    chunks, current = [], ""
    for unit in units:
        while len(unit) > size:
            head, unit = unit[:size], unit[size-overlap:]
            if current: chunks.append(current); current = ""
            chunks.append(head.strip())
        candidate = f"{current}\n\n{unit}".strip() if current else unit
        if len(candidate) <= size:
            current = candidate
        else:
            if current: chunks.append(current)
            prefix = current[-overlap:] if overlap and current else ""
            current = f"{prefix}\n{unit}".strip() if prefix else unit
            if len(current) > size: current = current[-size:]
    if current: chunks.append(current)
    return [c for c in chunks if c]


def build_chunks(docs: list[dict[str, Any]], size: int, overlap: int) -> list[dict[str, Any]]:
    chunks = []
    for doc in docs:
        for i, text in enumerate(split_text(doc["text"], size, overlap)):
            chunks.append({**{k:v for k,v in doc.items() if k != "text"}, "chunk_id": f"{doc['id']}::{i}", "text": text})
    log.info("CHUNKING_COMPLETE documents=%d chunks=%d", len(docs), len(chunks))
    return chunks
