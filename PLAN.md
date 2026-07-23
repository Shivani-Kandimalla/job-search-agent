# Job Search Agent — Full Relay Plan

This is the complete task breakdown for the group assignment, split into 5
sequential workstreams (one per team member). No team syncs/meetings are
required: each person finishes their workstream, makes the decisions that
are theirs to make, writes a handoff note in `handoff/`, and passes
concrete files forward to whoever picks up the next workstream.

Whoever picks up a workstream should read: (1) this file for their
workstream's scope, and (2) the previous workstream's handoff note in
`handoff/` for exactly what was delivered and any caveats.

---

## Foundation (Environment, Data, Filtering) — ✅ DONE

See `handoff/foundation_handoff.md` for full details of what was decided
and delivered.

**Summary:** environment/LLM provider setup, `data/jobs.csv` (23 real AI/ML
postings), `data/persona_preferences.json`, `data/portfolio.txt`,
`resume/resume.tex` + compiled `resume/resume.pdf` (1 page, verified),
`agent/tools/filtering.py` (tested: 7 kept / 16 rejected), filtering rules
written up in `report_draft.md`, `memory/memory.json` schema initialized.

---

## Scoring + Fit Analysis

**Receives:** everything in `handoff/foundation_handoff.md`.

**Decisions this workstream owns:**
- The scoring formula — signals and weights (e.g. `0.5*skill_match + 0.3*experience + 0.2*domain`) — pick defensible numbers and document the reasoning.
- Exactly how "skill match" is computed (exact string vs. fuzzy/synonym match, case-insensitivity, etc.).
- The fit-analysis prompt structure (as long as it produces the 5 required dimensions with citations).

**Steps:**
1. Build `agent/tools/scoring.py`: `score_job(job, resume_text, portfolio, master_skills, memory) -> score, breakdown`. Score against the whole profile — resume + every portfolio project + master skills list + memory contents, not just resume text.
2. Run scoring across the 7 kept jobs from `agent/tools/filtering.py`'s output, sort descending, auto-select Top 3 (no human input at this stage).
3. Confirm the Top 3 look sensible given the fictional persona; write the formula + weights into `report_draft.md`.
4. Build `agent/tools/fit_analysis.py`: one LLM call per Top-3 job, run once before any tailoring. Force all 5 dimensions in the output — Relevant Experience, Seniority, Education, Core Skills, Projects — each ✅/❌ citing something real (resume line, portfolio entry, master-skills entry, memory entry, or posting requirement).
5. Enforce the two-bucket missing-skills split in the prompt: evidenced-elsewhere (usable by tailoring later) vs. genuine gap (never to be added).
6. Require an explicit project-swap recommendation per job (weak resume project → better portfolio project + why), or an explicit "current projects are already optimal" statement.
7. Run on the real Top 3, read the output critically, tighten the prompt until nothing references a project/skill that doesn't literally exist in the input files.
8. Save one full fit-analysis example for the report.

**Handoff package** (`handoff/scoring_handoff.md`):
- `agent/tools/scoring.py` + a saved sample ranked Top-3 list with scores
- `agent/tools/fit_analysis.py` + one saved full fit-analysis output per Top-3 job (with ❌ items and swap suggestions — this becomes the next workstream's to-do list)
- Scoring formula writeup for the report

---

## Resume Tailoring

**Receives:** Top 3 jobs + their fit analyses (with ❌ items and swap suggestions) from the Scoring + Fit Analysis workstream.

**Decisions this workstream owns:**
- How the tailoring tool turns fit-analysis ❌ items into concrete edit instructions (structured LLM extraction, regex/section parsing, or manual mapping — your call).
- The one-page-overflow fix strategy (what gets trimmed first: summary length, bullet length, etc.).
- How the evidence-check is implemented (string containment, LLM-judged, etc. — just be consistent).

**Steps:**
1. Build `agent/tools/tailoring.py`, taking one Top-3 job + its fit analysis + `resume/resume.tex` + `data/portfolio.txt` as input.
2. Implement only the 4 allowed edits: rewrite Professional Summary, modify exactly 2 experience bullets, add/highlight aligned skills (surface-form alignment + additions only if evidenced), swap in a portfolio project (exact template formatting, must exist in `data/portfolio.txt`). Nothing else changes. Use the `AGENT-EDIT-TARGET` / `AGENT-SWAP-TARGET` comments already in `resume/resume.tex` to locate edit points programmatically.
3. Implement the Evidence Rule in code: reject any edit that can't be traced to resume/portfolio/master-skills/memory; log rejected ones as genuine gaps instead.
4. Automate `pdflatex` recompilation via subprocess after each edit; capture and handle compile errors. **Note:** this machine's LaTeX install needed `geometry` instead of `fullpage`, no `tabularx`, no `babel` — reuse `resume/resume.tex`'s working preamble, don't reintroduce those packages (see `handoff/foundation_handoff.md` for why).
5. Implement the One-Page Rule programmatically using `pypdf` (already in `requirements.txt`): `len(PdfReader(path).pages) == 1`. Auto-trim content and recompile in a loop until it's exactly one page.
6. Generate a change log per job: `{before, after, citation, reason}` for every edit.
7. Run manually on all 3 jobs, confirm each produces a clean, compiled, one-page, evidence-backed PDF with a sane change log.

**Handoff package** (`handoff/tailoring_handoff.md`):
- `agent/tools/tailoring.py`
- 3 tailored resumes: `outputs/<job_id>/resume_before.pdf` and `resume_after.pdf`
- 3 change logs (JSON or markdown) with citations — this is exactly what gets shown at the human pause
- One project-swap example for the report

---

## Human Review, Memory, Cover Letters

**Receives:** 3 tailored resumes + change logs from the Resume Tailoring workstream.

**Decisions this workstream owns:**
- The memory file's exact schema (finalize the Foundation workstream's sketch in `memory/memory.json` — fact, provenance, timestamp, job context).
- How review comments get parsed into "new facts" (LLM extraction call vs. simple heuristics).
- Cover letter format/tooling (LaTeX like the resume, or a simpler PDF library).

**Steps:**
1. Build the console review flow: print each job's change log (with citations) → prompt approve / reject+comments per resume.
2. Implement rework: feed rejection comments back into `agent/tools/tailoring.py` for another pass, capped at 2 rounds max; log `{round, feedback, actions_taken}` each round.
3. Implement fact extraction from comments (e.g. "I know GraphQL, add it" — this is deliberately NOT in `data/persona_preferences.json`'s master skills list, see the Foundation handoff notes) → apply immediately to the current rework AND to the remaining Top-3 jobs still being processed in the same run → write to `memory/memory.json` with provenance (`stated by candidate, review round N`).
4. Implement memory load-at-startup so remembered facts persist across runs.
5. Gate: only after approval does the pipeline proceed to compile final PDFs and move to cover letters — no other human gates anywhere else.
6. Build `agent/tools/cover_letter.py`: one PDF per approved job — contact header, greeting, opening naming the role+company with a hook from that job's Company Details field, 1-2 body paragraphs mapping real resume/portfolio experience to the job description, a skills line, closing. Same no-fabrication rule as tailoring.
7. Run a real test: reject one resume with a comment that teaches a genuinely new skill (not already in the master list — GraphQL is the intended one), confirm it lands in memory and gets reused on another job in the same run.

**Handoff package** (`handoff/review_handoff.md`):
- `agent/tools/cover_letter.py`, the human-review module, `memory/memory.json` (populated from your test run)
- The full review-round example (feedback → rework) and the memory example (comment → memory entry → reuse) written up for the report
- 3 approved final resumes + 3 cover letters in `outputs/<job_id>/`

---

## Orchestrator, Tracing, Full Run, Report/Demo Assembly

**Receives:** all finished, independently-tested tools from every prior workstream (filtering, scoring, fit_analysis, tailoring, human-review+memory, cover_letter) plus each workstream's report writeup.

**Decisions this workstream owns:**
- Tracing platform (Langfuse vs. LangSmith) and span structure/naming.
- The agent's system prompt and tool-calling design.
- Final report/demo structure and assembly.

**Steps:**
1. Build `agent/agent.py`: single LLM instance, one reasoning loop, register all 5 tools as callable functions with clear schemas — wiring already-tested pieces together, not building from scratch.
2. Write the system prompt so the LLM visibly reasons about why it's calling each tool next (required for grading on LLM Reasoning & Autonomy). Scoring is called as a tool but the score itself must never be LLM-generated.
3. Insert the single structural human pause after tailoring, before cover letters — a hard stop in the loop, not an LLM decision. No other human gates anywhere else.
4. Wrap every LLM call and tool call in tracing spans nested under one single root trace for the whole run; add explicit spans for the human-pause and the memory-write.
5. Reset memory, run the entire pipeline fresh end-to-end; deliberately reject one resume with a new-skill comment during the run so the trace captures a real memory-write moment.
6. Generate the public trace link, confirm it opens in an incognito window, screenshot the dashboard (tool-call spans, human-pause span, memory-update span, one reasoning-driven tool-selection span).
7. Assemble `outputs/` folders for ≥3 jobs: job details, resume before/after PDFs, cover letter PDF, fit analysis.
8. Compile the final report from everyone's writeups: architecture diagram, tool descriptions + prompt design, filtering rules, scoring formula, Top 3 + fit analyses, one swap example, one full review round, one memory example, trace link + screenshots, ethics reflection (bias in automated job matching, honesty in AI-edited resumes), team contributions table. Name it `GroupXX_JobSearchAgent_Report.pdf`.
9. Record the ≤10-minute live demo: dataset, agent executing and calling tools, ranked list + Top 3, a fit analysis with a swap suggestion, that swap visible in the final PDF, the human pause with at least one rejection+rework, a review comment writing a new fact to memory, final resume + cover letter PDFs, trace dashboard.
10. Finalize `README.md` (architecture diagram + setup/run instructions), confirm `.env` is gitignored, make the repo public or shared with the instructor, and test every link (repo, trace, demo) in an incognito window before submitting.
