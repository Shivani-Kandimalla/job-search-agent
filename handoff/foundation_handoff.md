# Handoff: Foundation → Scoring + Fit Analysis

## Decisions made
- LLM provider: local Ollama (`llama3.2`), OpenAI-compatible endpoint. See `README.md`.
- Repo structure: `data/`, `resume/`, `agent/tools/`, `memory/`, `outputs/`, `handoff/`.
- Memory file schema: `memory/memory.json` — `{"skills_learned": [...], "other_facts": [...]}`.
- Fictional persona: "Jordan Ellis", M.S. Data Science, 4 years experience,
  Data Scientist / ML Engineer background in Healthcare + Retail/E-commerce.

## Files delivered
- `data/jobs.csv` — 23 real AI/ML job postings, all 9 required fields, manually
  sourced (via search, not scraped) on 2026-07-23. Generated via
  `scripts/build_jobs_csv.py` (for correct CSV escaping only).
- `data/persona_preferences.json` — locations, years experience, excluded
  companies, target job titles, master skills list. Note: `GraphQL` and
  `Terraform` are deliberately NOT in the master skills list — reserved for
  the memory/review-pause demo further down the pipeline.
- `data/portfolio.txt` — 7 projects across 4 domains (Healthcare, Retail/
  E-commerce, Banking/Fintech, Construction Technology). Projects 1-3 are
  marked `[ON RESUME]` and must appear in `resume.tex` once it exists;
  projects 4-7 are portfolio-only, including a Construction Technology
  computer-vision project that lines up with kept job J18.
- `agent/tools/filtering.py` — deterministic filtering tool,
  `filter_jobs(jobs, preferences) -> (kept, rejected)`. Tested against the
  real 23-job dataset: **7 kept, 16 rejected**, every rejection has a
  specific logged reason (company exclusion / title mismatch / location
  mismatch / experience gap). Run `python agent/tools/filtering.py` from the
  repo root (with venv activated) to see the full kept/rejected printout.
- `report_draft.md` — filtering rules explained in plain English, ready to
  paste into the final report.
- `memory/memory.json` — empty, schema-only starting file.

## Resume — done
- `resume/resume.tex` — filled in from the instructor's `sample_resume.tex`
  template (kept at repo root, untouched, for reference) with the "Jordan
  Ellis" persona. Contains exactly the 3 "[ON RESUME]" projects from
  `data/portfolio.txt` (Patient Readmission Risk Predictor, E-commerce
  Product Recommendation Engine, Customer Support RAG Chatbot), formatted
  identically. `AGENT-EDIT-TARGET` / `AGENT-SWAP-TARGET` comments were kept
  intact for the Resume Tailoring workstream's programmatic edits.
- `resume/resume.pdf` — compiled with `pdflatex`, confirmed **exactly 1
  page** both by pdflatex's own report and independently via `pypdf`
  (`len(PdfReader("resume.pdf").pages) == 1`).
- Local LaTeX toolchain note: BasicTeX was installed via
  `brew install --cask basictex`, with `/Library/TeX/texbin` added to PATH.
  The template's `fullpage` and `babel` packages weren't reliably available/
  working in this environment and were removed with no visual difference —
  `fullpage` replaced by `\usepackage[margin=1in]{geometry}` (kept working
  with the template's existing `\addtolength` margin tweaks), `tabularx`
  removed (unused — the template only relies on the built-in `tabular*`
  environment), `babel` removed (non-essential, just English hyphenation).
  Whoever picks up Resume Tailoring should reuse this same working
  `resume.tex` preamble when generating per-job resume variants — don't
  reintroduce those three packages.
- `pypdf` was added to `requirements.txt` — needed by the Resume Tailoring
  workstream's one-page verification tool anyway, installed and tested now.

## What to build next (Scoring + Fit Analysis)
See the 7 kept jobs above — that's your scoring input. Use
`data/jobs.csv`, `data/portfolio.txt`, `data/persona_preferences.json`
(master skills list + years of experience), and `memory/memory.json`
(currently empty) as the four inputs to `score_job(...)`.

See `PLAN.md` for the full workstream breakdown (steps, decisions owned,
and what to hand off next).
