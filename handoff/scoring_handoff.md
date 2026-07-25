# Handoff: Scoring + Fit Analysis → Resume Tailoring

## Decisions made
- Scoring formula: `score = 0.5*skill_match + 0.3*experience_alignment + 0.2*domain_alignment`,
  fully deterministic (no LLM). See `report_draft.md` for the full writeup
  and rationale.
- Skill matching allows a small hand-curated synonym table (ML ↔ Machine
  Learning, RAG ↔ Retrieval-Augmented Generation, etc.) plus a token-overlap
  fallback for multi-word skills — see `SKILL_SYNONYMS` in
  `agent/tools/scoring.py`.
- Fit Analysis divides work between deterministic Python (Seniority,
  Education, Core Skills — anything with an objectively-checkable answer)
  and one LLM call per job (Relevant Experience, Projects, project-swap
  recommendation, overall summary — anything that needs real judgment).
  This split exists because the local `llama3.2` model was unreliable at
  simple arithmetic/keyword-matching tasks (e.g. it would mark a candidate
  with more years than required as failing "Seniority") but fine at
  qualitative narrative once given the deterministic facts as ground truth.
- Project-swap suggestions are validated in code, not trusted from the
  model: a swap is only "recommended" if both project names it returns
  exactly match a real project in `data/portfolio.txt`. Otherwise the
  suggestion is discarded and replaced with an honest "current projects
  already optimal" fallback. This is the Evidence Rule enforced in code.
- Missing-skill two-bucket split (`evidenced_elsewhere` vs. `genuine_gap`)
  is computed once in `fit_analysis.classify_required_skills(...)` and
  handed to the LLM as fixed ground truth it cannot contradict.

## Files delivered
- `agent/tools/profile.py` — shared loader used by every downstream tool
  (Scoring, Fit Analysis, and now Tailoring too). Gives you, in one call to
  `load_full_profile()`:
  - `resume_text` (raw `.tex`) and `resume_plaintext` (regex-stripped,
    readable — safe to feed an LLM without confusing it with LaTeX markup)
  - `degree_fields` (parsed straight out of the resume's Education section)
  - `portfolio_text` (raw) and `portfolio_projects` (parsed list of dicts:
    `name`, `on_resume` bool, `domain`, `tech_stack` list, `description`)
  - `master_skills`, `candidate_years`, `candidate_name`, `preferences`
  - `memory` (raw dict) and `memory_skills` (flat list)
  - Also exposes `split_skills(skills_str)` — use this, not `.split(",")`,
    whenever you parse a job's `required_skills` field: some skills contain
    a comma inside parentheses (e.g. `computer vision (YOLO, Segment
    Anything)`) and naive splitting breaks them into two garbage fragments.
- `agent/tools/llm_client.py` — shared `chat(messages, ...)` helper wrapping
  the Ollama/OpenAI client (same env vars as `test_llm.py`). Reuse this for
  Tailoring/Cover Letters instead of re-deriving the client setup. Supports
  `response_format={"type": "json_object"}` — Ollama honors this and it
  measurably improves JSON reliability from `llama3.2`, use it whenever you
  need structured output back.
- `agent/tools/scoring.py` — `score_job(job, profile) -> breakdown dict`,
  `score_and_rank(jobs, profile)`, `top_n(jobs, profile, n=3)`. Run
  `python agent/tools/scoring.py` to reproduce; saves
  `outputs/ranked_jobs.json` (full ranking + `top3_job_ids`).
- `agent/tools/fit_analysis.py` — `analyze_fit(job, profile, score_breakdown) -> dict`
  and `format_report(analysis) -> str`. Run `python agent/tools/fit_analysis.py`
  to reproduce; saves `outputs/<job_id>/fit_analysis.json` and `.txt` for
  each Top-3 job.

## Top 3 jobs (auto-selected, saved in `outputs/ranked_jobs.json`)
1. **J18** — AI Engineer: Computer Vision, LLMs & ML @ Flexgen Construction
   Technology — score 0.90
2. **J21** — Sr Applied Data Scientist, Search & Browse @ Target — score 0.86
3. **J14** — MLOps Engineer / ML Engineer (Remote) @ Experian Health — score 0.77

## Fit analyses — this is your to-do list
Each `outputs/<job_id>/fit_analysis.json` contains everything Tailoring
needs, notably:
- `skill_buckets.evidenced_elsewhere` — skills you're allowed to surface on
  the resume (they're real, just not on the resume text yet).
- `skill_buckets.genuine_gap` — skills you must never add.
- `project_swap` — `{recommended, weak_resume_project, better_portfolio_project, reasoning}`.
  Only J21 got a validated swap recommendation this run (replace
  "E-commerce Product Recommendation Engine" with "Demand Forecasting for
  Retail Supply Chain"); J18 and J14 came back "already optimal" — that's
  a legitimate outcome, not a bug, but feel free to re-run
  `fit_analysis.py` (it's stochastic at temperature 0.2) if you want a
  second swap example for variety.
- `relevant_experience`, `education`, `seniority`, `core_skills`,
  `projects` — the 5 required dimensions, each with `status` (`check`/`x`)
  and a `citation` you can quote directly in tailored bullet points.

## What to build next (Resume Tailoring)
Take one Top-3 job's `outputs/<job_id>/fit_analysis.json` + `resume/resume.tex`
+ `data/portfolio.txt` as input to `agent/tools/tailoring.py`. Use the
`AGENT-EDIT-TARGET` / `AGENT-SWAP-TARGET` comments already in `resume.tex`
to locate edit points programmatically. Reuse `resume/resume.tex`'s working
preamble (`geometry`, no `tabularx`/`babel`/`fullpage`) when recompiling —
see `handoff/foundation_handoff.md` for why.

See `PLAN.md` for the full workstream breakdown.
