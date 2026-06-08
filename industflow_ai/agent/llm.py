"""Ollama chat-model factory. Local-first per the project brief."""
from __future__ import annotations

from langchain_ollama import ChatOllama

from ..config import AGENT_MODEL, LLM_TEMPERATURE, OLLAMA_BASE_URL


def get_chat_model(model: str | None = None, temperature: float | None = None,
                   **kwargs) -> ChatOllama:
    """Return a configured ChatOllama instance.

    qwen3 emits <think> reasoning blocks by default; we disable that
    (`reasoning=False`) so tool-calling responses stay clean and fast.
    """
    return ChatOllama(
        model=model or AGENT_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=LLM_TEMPERATURE if temperature is None else temperature,
        reasoning=False,
        **kwargs,
    )
