# Job Search Agent — Group Assignment

Single LLM-based AI agent that takes a candidate profile, finds best-matching
jobs from a real dataset, explains fit, tailors a one-page resume (LaTeX →
PDF), pauses once for human approval (with memory), and generates cover
letters.

## Decisions locked in during the Foundation workstream

- **LLM provider:** Local **Ollama** running `llama3.2`. No paid API key
  required. Ollama's OpenAI-compatible endpoint (`/v1`) is used via the
  `openai` Python SDK, so swapping to a real OpenAI/Anthropic key later only
  means changing `.env` — no code changes needed elsewhere.
- **Repo folder structure:**
  ```
  data/            jobs.csv, persona_preferences.json, portfolio.txt
  resume/          resume.tex, compiled PDFs
  agent/tools/     filtering.py, scoring.py, fit_analysis.py, tailoring.py, cover_letter.py
  agent/agent.py   the single-agent orchestrator (built in the final workstream)
  memory/          memory.json (written/read by the agent at runtime)
  outputs/         one folder per job: job details, resume before/after, cover letter, fit analysis
  handoff/         workstream-to-workstream handoff notes (this is our "no meetings" sync mechanism)
  ```
- **Memory file format:** JSON. Schema:
  ```json
  {
    "skills_learned": [
      {
        "skill": "GraphQL",
        "source": "stated by candidate, review round 1",
        "job_id": "J07",
        "timestamp": "2026-07-23T00:00:00"
      }
    ],
    "other_facts": []
  }
  ```

## Environment setup (already done)

```bash
python3 -m venv venv
source venv/bin/activate        # Mac/Linux
pip install -r requirements.txt
```

`.env` contents (Ollama, no real API key needed):
```
OPENAI_API_KEY=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.2
```

Ollama must be running locally (`ollama serve`, or the desktop app) with the
model pulled: `ollama pull llama3.2`.

## Minimal LLM access snippet (copy this pattern everywhere)

```python
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY", "ollama"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
)

response = client.chat.completions.create(
    model=os.getenv("OLLAMA_MODEL", "llama3.2"),
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

Tested working — see `test_llm.py`.

## LaTeX (for resume compilation and later resume tailoring)

Installed via Homebrew BasicTeX:
```bash
brew install --cask basictex
echo 'export PATH="/Library/TeX/texbin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```
Verify: `pdflatex --version`. Missing packages get installed on demand:
```bash
sudo tlmgr install <package-name>
```

## Pipeline workstreams / ownership

See `PLAN.md` for the full relay plan (what each workstream builds, the
decisions it owns, and the handoff package it produces), and `handoff/`
for the actual handoff notes written as each workstream completes.
