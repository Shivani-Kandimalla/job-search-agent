"""
Shared LLM client factory. Every tool that needs a model call (Fit
Analysis, Tailoring, Cover Letters, ...) should get its client from here
instead of re-deriving the Ollama/OpenAI setup, so switching from local
Ollama to a real OpenAI/Anthropic key is a one-place change.

Mirrors the exact env vars test_llm.py already uses.
"""

import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def get_client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY", "ollama"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    )


def get_model() -> str:
    return os.getenv("OLLAMA_MODEL", "llama3.2")


def chat(messages: list, temperature: float = 0.2, **kwargs) -> str:
    """One-shot chat completion, returns the plain text content."""
    client = get_client()
    response = client.chat.completions.create(
        model=get_model(),
        messages=messages,
        temperature=temperature,
        **kwargs,
    )
    return response.choices[0].message.content
