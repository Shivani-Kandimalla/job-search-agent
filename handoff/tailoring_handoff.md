# Handoff: Resume Tailoring → Human Review, Memory, Cover Letters

## Decisions made

- **Which 2 bullets get rewritten** was already fixed by the template's own
  `AGENT-EDIT-TARGET: experience-bullet-1`/`-2` markers (both on the
  current "Data Scientist @ Meridian Health Analytics" role) -- no
  extraction logic needed to "pick" which two.
- **Evidence Rule for skill additions is code-level, not LLM-trusted.**
  The LLM is never asked which skills to add. `agent/tools/tailoring.py`'s
  `_skills_to_add()` reads straight from `fit_analysis["skill_buckets"]`
  (Stage 2's own deterministic, Python-computed string match), and adds
  exactly two kinds of entries to a new "Additional (aligned with this
  role):" skills line:
  - **surface-form alignment**: an `on_resume` bucket skill that isn't
    literally the resume's own wording (e.g. the job says "GenAI/RAG
    systems", the resume only says "RAG" -- Stage 2's scoring already
    counted it matched via synonym/token overlap, so it's real, just
    worded differently) -- see J21's change log.
  - **evidenced additions**: `evidenced_elsewhere` bucket skills (real,
    just not yet listed) -- see J18's "vector databases" and "computer
    vision (YOLO, Segment Anything)".
  Anything in `genuine_gap` is logged in the change log under a
  `"skills (not applied)"` section with an explicit reason -- visible,
  not silently dropped.
- **Project swap is executed, never re-decided.** `fit_analysis.json`'s
  `project_swap` field was already produced *and fact-checked* against
  `data/portfolio.txt` in Stage 2 (see `handoff/scoring_handoff.md`).
  Tailoring only looks up the named project and swaps it in if
  `recommended: true`. The swapped-in project keeps the **replaced
  project's original year** (portfolio.txt has no per-project year field,
  so reusing the old slot's year avoids inventing a new fact).
- **Anti-fabrication guard is numeric, not semantic.** The one LLM call
  (summary + 2 bullet rewrites + the swapped project's resume bullet, if
  any) is checked in code:
  - Every number in an **original bullet** must appear, **unchanged**, in
    its rewrite (`_same_numbers`) -- no dropped, changed, or invented
    metrics.
  - The **summary** and the **swapped-project bullet** may state numbers
    only if those numbers are traceable to the real resume text / real
    portfolio description respectively (`_no_new_numbers`).
  A failed check gets one correction turn (a real second LLM call, same
  self-correction pattern `fit_analysis.py` already uses), then falls back
  to the original bullet unchanged (or a plain truncation of the real
  portfolio description for a swap bullet) -- logged in the change log
  either way. In the actual run below, all three jobs passed on the first
  or corrected attempt; the fallback path exists but wasn't exercised.
- **One-Page Rule trim order** (`_enforce_one_page` in `tailoring.py`,
  capped at 5 recompile attempts): shorten the summary first, then the 2
  bullets, then drop the lowest-priority added skill(s) last -- summary is
  the least information-dense edit, skills are the cheapest content to
  lose. Not exercised in the actual run (all 3 tailored resumes compiled
  to exactly 1 page on the first pass), but implemented and testable by
  temporarily lowering the character budgets in `_enforce_one_page`.
- **`tailor_resume(job, fit_analysis, profile, revision_feedback=None)`**
  already accepts an optional `revision_feedback` string, appended to the
  LLM prompt when present. This is unused by Stage 3 but is the hook
  `PLAN.md` says Stage 4 needs ("feed rejection comments back into
  tailoring.py for another pass") -- call `tailor_resume(...)` again with
  the reviewer's comment in that param for a rework round; it re-derives
  everything from scratch (safe to call repeatedly, doesn't mutate
  `resume/resume.tex`).

## Files delivered

- `agent/tools/tailoring.py` -- `tailor_resume(job, fit_analysis, profile,
  revision_feedback=None) -> dict` (`{job_id, tex_path, pdf_path,
  before_pdf_path, change_log}`). Run `python agent/tools/tailoring.py`
  from the repo root to reproduce all 3 Top-3 jobs.
- Per job, in `outputs/<job_id>/`:
  - `resume_before.pdf` -- untouched copy of `resume/resume.pdf`
  - `resume_tailored.tex`, `resume_after.pdf` -- the tailored, compiled,
    verified-one-page resume
  - `change_log.json` / `change_log.md` -- every edit (and every
    considered-but-rejected skill/edit) as `{section, before, after,
    citation, reason}` -- **this is exactly what Stage 4's human-review
    pause should print per job.**

## One project-swap example (for the report)

**J18 -- AI Engineer: Computer Vision, LLMs & ML @ Flexgen Construction
Technology.** Removed: "E-commerce Product Recommendation Engine" (Retail
/ E-commerce, Python/PyTorch/embeddings/Redis). Added: "Construction Site
Safety Vision Monitor" (Construction Technology, Python/PyTorch/YOLO/
OpenCV/edge deployment) -- straight from Stage 2's fact-checked
`project_swap` field. Reasoning: "This project aligns more closely with
the required skills and domain of construction technology." Visually
confirmed in `outputs/J18/resume_after.pdf`: the new project entry is
formatted identically to the template's other project entries, the other
two projects are byte-for-byte untouched, and the PDF is still exactly one
page.

## Known caveat carried over from Stage 2 (not fixed here, flagging for the report)

`outputs/J14/fit_analysis.json` has a small internal inconsistency between
its two independently-computed grounding-fact fields: `score_breakdown`
(from `scoring.py`, which checks skill evidence against one combined
resume+portfolio+master-skills+memory text blob) lists `"Kubernetes
(EKS)"` as matched, while `skill_buckets` (from `fit_analysis.py`, which
checks resume text and "everything else" as two *separate* lookups) buckets
it as a `genuine_gap`. Root cause: the required skill's second token
("EKS") never appears anywhere in the candidate's real materials, only
"Kubernetes" does (master skills list says "Kubernetes (basic)") -- the
combined-blob token-overlap check in `scoring.py` and the two-stage check
in `fit_analysis.py` disagree on whether that's enough to count as a
match. This is a Stage 2 scoring/fit-analysis discrepancy, not a Stage 3
bug -- Tailoring deliberately only trusts `skill_buckets` (per Stage 2's
own handoff note: "Use this one ... when deciding what's safe to add"), so
the more conservative reading won and `"Kubernetes (EKS)"` was correctly
**not** added to the resume. Worth a one-line mention in the report's
scoring-formula section if Person 2's writeup gets revisited, but doesn't
block Stage 3 or 4.

## Environment note for whoever runs this next (Windows-specific)

This workstream was executed on Windows, while Stages 1-2 were built on
Mac. Two environment gaps had to be closed here, both already resolved on
this machine and worth checking on any other machine that picks this up:
- **LaTeX**: needs `pdflatex` on PATH. `tailoring.py`'s `_find_pdflatex()`
  checks PATH, then a `PDFLATEX_PATH` env var override, before giving up
  -- set that env var if `pdflatex` isn't on PATH rather than editing the
  code.
- **LLM**: Ollama + `llama3.2` installed locally (matches Stage 1's
  locked-in choice in `README.md`), free, no API key. `python
  test_llm.py` confirms connectivity.
- A dedicated conda env `job-search-agent` (Python 3.11) was created for
  this project (`conda activate job-search-agent`), consistent with the
  other course-project conda envs on this machine, in place of the
  Mac-side `venv` the README describes -- either works, `requirements.txt`
  is the same either way.

## What to build next (Human Review, Memory, Cover Letters)

Print each job's `outputs/<job_id>/change_log.md` (already citation-backed
and human-readable) at the review pause, prompt approve/reject+comments,
and on rejection call `tailor_resume(job, fit_analysis, profile,
revision_feedback=<the comment>)` again for a rework round (capped at 2
per `PLAN.md`). See `PLAN.md`'s "Human Review, Memory, Cover Letters"
section for the full scope.
