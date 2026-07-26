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
- **Memory file format:** JSON, written and read by
  `agent/tools/memory_store.py`. Final schema (the two top-level keys are
  the Foundation workstream's; the per-entry provenance fields were
  finalized by the Human Review workstream):
  ```json
  {
    "skills_learned": [
      {
        "skill": "MLflow",
        "source": "stated by candidate",
        "review_round": 1,
        "job_id": "J18",
        "comment": "<verbatim reviewer comment the fact came from>",
        "timestamp": "2026-07-25T20:24:07"
      }
    ],
    "other_facts": []
  }
  ```
  `other_facts` entries use the same fields with `fact` instead of `skill`.
  The file is loaded at startup by `profile.load_full_profile()`, so
  remembered skills count as evidence in scoring, fit analysis, resume
  tailoring and cover letters on every later run.

## Environment setup (already done)

```bash
python3 -m venv venv
source venv/bin/activate        # Mac/Linux
pip install -r requirements.txt
```

### Ollama setup (if not already installed on your machine)

1. Install Ollama from https://ollama.com/download (Mac/Windows/Linux).
2. Pull the model this project uses: `ollama pull llama3.2`
3. Make sure the Ollama server is running: `ollama serve` (or just open the
   Ollama desktop app — it runs the server in the background).
4. Create a `.env` file in the repo root (this file is git-ignored, so
   you'll need to create it yourself even after cloning) with:
   ```
   OPENAI_API_KEY=ollama
   OLLAMA_BASE_URL=http://localhost:11434/v1
   OLLAMA_MODEL=llama3.2
   ```
5. Verify everything works end-to-end: `python test_llm.py` should print a
   live response from the model.

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

On Linux (or anywhere you don't have root), TinyTeX installs a working
`pdflatex` into your home directory instead:
```bash
wget -qO- "https://yihui.org/tinytex/install-bin-unix.sh" | sh
export PATH="$HOME/.TinyTeX/bin/x86_64-linux:$PATH"
tlmgr install titlesec enumitem      # the two packages resume.tex needs
```
If `pdflatex` isn't on `PATH`, set `PDFLATEX_PATH` to its full path rather
than editing the code — `tailoring.py` checks that env var.

## Tools built so far (run from the repo root, venv activated)

```bash
python agent/tools/filtering.py       # deterministic filter: 23 jobs -> 7 kept
python agent/tools/scoring.py         # deterministic scoring of the 7 kept jobs -> Top 3
python agent/tools/fit_analysis.py    # one LLM call per Top-3 job -> outputs/<job_id>/fit_analysis.{json,txt}
python agent/tools/tailoring.py       # tailors + recompiles a 1-page resume per Top-3 job -> outputs/<job_id>/
python agent/tools/human_review.py    # the ONE human pause: change logs -> approve/reject -> memory -> cover letters
python agent/tools/cover_letter.py    # (standalone) regenerate the 3 cover letter PDFs
python agent/tools/memory_store.py    # print memory/memory.json with provenance
```

The review pause takes console input. Useful flags:

```bash
python agent/tools/human_review.py --reset-memory     # start from empty memory (clean end-to-end run)
python agent/tools/human_review.py --no-cover-letters # stop after the pause
python agent/tools/human_review.py --script scripts/demo_review_script.json  # replay a canned reviewer session
```

`agent/tools/profile.py` and `agent/tools/llm_client.py` are shared helpers
(profile/resume/portfolio loading, and the Ollama chat client respectively)
used by every tool above and meant to be reused by Tailoring and Cover
Letters too — see `handoff/scoring_handoff.md` for what they expose.

## Pipeline workstreams / ownership

See `PLAN.md` for the full relay plan (what each workstream builds, the
decisions it owns, and the handoff package it produces), and `handoff/`
for the actual handoff notes written as each workstream completes.
