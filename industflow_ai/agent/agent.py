"""The natural-language Q&A agent (LangChain v1 `create_agent` + Ollama).

The agent picks among the read-only tools in `tools.py`, executes them, and
answers in plain language. Every answer is written to the audit log together
with the tools it invoked.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from ..audit.log import record
from ..config import REPORT_LANG
from .llm import get_chat_model
from .tools import ALL_TOOLS

_LANG_NAME = {"es": "Spanish", "en": "English"}

_SYSTEM = (
    "You are a production-intelligence assistant for an Industflow manufacturing "
    "line. Answer questions about production data by calling the provided tools — "
    "never invent numbers. Prefer the specific predefined tools; use "
    "`mongo_aggregate` only for questions none of them cover. When a question "
    "names a line, call `list_lines` first to resolve its id. When a question asks "
    "for the worst/top N steps, pass the right tool arguments (min_attempts, "
    "limit, worst_first/sort_by) instead of eyeballing a long list. Keep answers "
    "concise: a direct answer plus the concrete figures, no padded generic "
    "recommendations. Your role is interpretation and summarization; you do not "
    "make operational decisions. Answer in {lang}."
)


@lru_cache(maxsize=1)
def get_agent():
    """Build (once) the compiled agent graph."""
    llm = get_chat_model()
    lang = _LANG_NAME.get(REPORT_LANG, "English")
    return create_agent(llm, tools=ALL_TOOLS, system_prompt=_SYSTEM.format(lang=lang))


def ask(question: str) -> dict[str, Any]:
    """Run the agent on a question. Returns answer + tools used; audited."""
    agent = get_agent()
    result = agent.invoke({"messages": [HumanMessage(question)]})
    messages = result["messages"]

    # Name + arguments of every tool call the model made (for the audit trail).
    tool_calls = [
        {"tool": tc.get("name"), "args": tc.get("args")}
        for m in messages if isinstance(m, AIMessage)
        for tc in (m.tool_calls or [])
    ]
    answer = messages[-1].content if messages else ""

    record("qa", input=question, tools_used=tool_calls,
           result_summary={"answer": answer[:4000], "chars": len(answer)})
    return {"question": question, "answer": answer,
            "toolsUsed": [t["tool"] for t in tool_calls]}
