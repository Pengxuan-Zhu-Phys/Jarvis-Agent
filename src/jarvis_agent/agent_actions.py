from __future__ import annotations


INDEX_ACTION_MARKER = "[ACTION: INDEX]"

AGENT_SYSTEM_PROMPT = f"""You are Jarvis-Agent, a local assistant for HEP software packages.

You can answer normal questions with the configured local model. When the user clearly asks to index,
scan, update, or rebuild the current project's code index or symbol table, emit exactly the marker
`{INDEX_ACTION_MARKER}` on a single line.

Do not explain that marker. The runtime will execute the project indexer and return the result.
"""


INDEX_INTENT_PHRASES = (
    "索引",
    "代码索引",
    "项目索引",
    "更新索引",
    "更新一下代码索引",
    "扫描",
    "扫描一下",
    "代码结构",
    "项目结构",
    "符号表",
    "建立符号表",
    "重建符号表",
    "重新建立符号表",
    "index",
    "reindex",
    "code index",
    "project index",
    "scan project",
    "scan code",
    "code structure",
    "symbol table",
    "rebuild symbols",
)


def detect_agent_action(text: str) -> str | None:
    normalized = normalize_text(text)
    if not normalized:
        return None
    if detect_action_marker(text) == "index":
        return "index"
    if any(phrase in normalized for phrase in INDEX_INTENT_PHRASES):
        return "index"
    return None


def detect_action_marker(text: str) -> str | None:
    marker = INDEX_ACTION_MARKER.lower()
    for line in text.splitlines():
        if line.strip().lower() == marker:
            return "index"
    return None


def normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())
