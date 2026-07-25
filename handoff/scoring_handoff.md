# Handoff: Scoring + Fit Analysis → Resume Tailoring

## Decisions made
- Scoring formula: `score = 0.5*skill_match + 0.3*experience_alignment + 0.2*domain_alignment`,
  fully deterministic (no LLM). See `report_draft.md` for the full writeup
  and rationale.
- Skill matching allows a small hand-curated synonym table (ML ↔ Machine
  Learning, RAG ↔ Retrieval-Augmented Generation, etc.) plus a token-overlap
  fallback for multi-word skills — see `SKILL_SYNONYMS` in
  `agent/tools/scoring.py`.
- **Important correction made mid-workstream:** an earlier version of
  `fit_analysis.py` computed Seniority/Education/Core Skills verdicts in
  pure Python (no LLM call at all) because the local model was unreliable
  at that arithmetic. That directly conflicts with the assignment's own
  rules — Section 3.2 explicitly calls Scoring "deterministic; NOT an LLM
  call," but Section 3.3 never says that about Fit Analysis (it's framed
  purely as an LLM narrative task), and the assignment's global rule is
  "The LLM drives — hard-coded scripts that execute fixed steps without
  LLM decision-making will lose points." **The current version has all 5
  dimensions decided and written by the LLM itself**, in one call. Python
  only supplies accurate reference facts (skill-evidence buckets, years
  comparison, degree comparison) as grounding context in the prompt — it
  never overwrites what the model decided. Keep it this way; don't
  reintroduce a Python override for these fields.
- Project-swap suggestions get a **fact-check, not a judgment override**:
  if the model names a project that doesn't exist in `data/portfolio.txt`,
  it gets one self-correction turn (a second, visible LLM call listing the
  real project names) before the tool ever falls back to "no swap." This
  preserves the model's own reasoning about *which* project fits better
  while still enforcing the assignment's Evidence Rule ("no evidence means
  no edit") on project *names* specifically.
- Same fact-check pattern applied to **Seniority** after final testing found
  it self-contradicting in 2 of 3 saved runs (e.g. citing "candidate has 4
  years, posting requires 3+" and still marking it ❌ — its own rule 6 says
  mark ❌ only when they "clearly fall short"). `analyze_fit()` now gives the
  model one self-correction turn quoting its own contradictory text back to
  it before falling back to a disclosed auto-correction. Same spirit as the
  project-swap check: candidate_years ≥ min_years_required is a plain
  arithmetic fact already in the model's reference data, so catching the
  model disagreeing with its own arithmetic isn't a judgment override.
- Missing-skill two-bucket split (`evidenced_elsewhere` vs. `genuine_gap`)
  is computed once in `fit_analysis.classify_required_skills(...)` and
  handed to the LLM as reference facts; the model reproduces this split
  into its own `core_skills.missing_evidenced` / `core_skills.genuine_gap`
  output fields (matching the assignment's example format) rather than
  Python writing those fields directly.

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
needs. Two different things live in there, and they're not the same
source — know which one to trust for what:
- `skill_buckets` (top-level, Python-computed, deterministic) —
  `{on_resume, evidenced_elsewhere, genuine_gap}`. **Use this one** when
  deciding what's safe to add to the resume — it's a guaranteed-accurate
  string match against the real profile files, not the LLM's
  recollection of it.
- `core_skills` (nested inside the LLM's own output) —
  `{aligned, missing_evidenced: [{skill, evidence}], genuine_gap}`. This
  is the model's own reproduction of the same split, worded for the
  human-readable report. Fine to quote in the report/change-log text, but
  don't treat it as more authoritative than `skill_buckets` for deciding
  actual resume edits.
- `relevant_experience`, `seniority`, `education` — `{status, citation, explanation}`,
  all written by the LLM itself (see "Decisions made" above for why —
  don't reintroduce a Python override here).
- `projects` — `{current_weak_project, weak_project_note, swap_suggestion: {project, reasoning} or null, already_optimal}`.
- `project_swap` — the fact-checked version of the same swap decision:
  `{recommended, weak_resume_project, better_portfolio_project, reasoning}`.
  Use `project_swap`, not the raw `projects` field, when deciding whether
  to actually perform a swap — `project_swap` is guaranteed to reference a
  real project (or be `recommended: false`), while `projects` is the raw
  LLM output before that fact-check. In the current saved run, **J18** got
  a validated swap (replace "E-commerce Product Recommendation Engine"
  with "Construction Site Safety Vision Monitor"); J14 and J21 came back
  "already optimal."
  **Important: `fit_analysis.py` calls a live local LLM, so re-running it
  WILL change which job(s) get a swap suggestion** — this has already
  happened twice during testing (J14 got it first, then J18). Don't
  hard-code "J14 gets the swap" anywhere in Tailoring's own code or report
  text — always read `project_swap` fresh out of whichever
  `outputs/<job_id>/fit_analysis.json` is on disk at the time, and if you
  re-run `fit_analysis.py` yourself, re-check every doc/report snippet
  that quotes a specific job/project pairing so nothing drifts out of
  sync.

## What to build next (Resume Tailoring)
Take one Top-3 job's `outputs/<job_id>/fit_analysis.json` + `resume/resume.tex`
+ `data/portfolio.txt` as input to `agent/tools/tailoring.py`. Use the
`AGENT-EDIT-TARGET` / `AGENT-SWAP-TARGET` comments already in `resume.tex`
to locate edit points programmatically. Reuse `resume/resume.tex`'s working
preamble (`geometry`, no `tabularx`/`babel`/`fullpage`) when recompiling —
see `handoff/foundation_handoff.md` for why.

See `PLAN.md` for the full workstream breakdown.
