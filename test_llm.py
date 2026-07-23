"""
Minimal LLM connectivity test.

Uses a local Ollama server via the OpenAI-compatible API, so no paid
API key is required. Ollama must be running (`ollama serve`, or the
Ollama desktop app) and the model below must be pulled
(`ollama pull llama3.2`).

If you'd rather use a real OpenAI/Anthropic account, swap the
base_url/api_key lines for your real OPENAI_API_KEY and drop base_url.
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY", "ollama"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
)

model = os.getenv("OLLAMA_MODEL", "llama3.2")

response = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Hello"}],
)

print(response.choices[0].message.content)
