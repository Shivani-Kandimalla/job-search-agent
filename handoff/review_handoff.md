# Handoff: Human Review + Memory + Cover Letters → Orchestrator, Tracing, Full Run

## Decisions made

- **Memory schema finalized** (`agent/tools/memory_store.py`). The two
  top-level keys the Foundation workstream sketched are unchanged, so
  `profile.load_full_profile()` / `profile.memory_skills()` keep working
  untouched; what this workstream pinned down is the per-entry provenance:
  ```json
  {"skill": "MLflow", "source": "stated by candidate", "review_round": 1,
   "job_id": "J18", "comment": "<verbatim reviewer comment>",
   "timestamp": "2026-07-25T20:24:07"}
  ```
  `other_facts` entries have the same fields with `fact` instead of
  `skill`. `memory_store.citation_for(skill)` renders an entry as an
  Evidence-Rule citation string ("memory.json (stated by candidate, review
  round 1, while reviewing J18)"), which is what the change logs, the
  review logs and the cover letter's skill citations all print.
- **Review comments are split by an LLM, then guarded by code.** A comment
  mixes candidate FACTS ("I've used MLflow") with TAILORING INSTRUCTIONS
  ("the summary is too generic"); only the first kind may be remembered.
  One LLM call does the split (it's a language judgment, not a rule), then
  `_stated_in_comment()` throws away any "extracted" skill whose text
  isn't literally in the reviewer's own comment. This guard fired in the
  recorded run: the model proposed the fact *"I'm open to hybrid roles in
  Seattle"*, which the reviewer never wrote -- it was rejected and logged
  as `MEMORY REJECTED`, and never reached `memory/memory.json`.
- **Cover letters are LaTeX + `pdflatex`, not a separate PDF library.**
  Zero new dependencies (pdflatex is already required by `tailoring.py`),
  the letter matches the resume visually, and the one-page check is the
  same `pypdf` page count. `cover_letter.py` imports `_compile`,
  `_page_count`, `_latex_escape`, `_no_new_numbers`, `_shorten` and
  `_extract_summary` from `tailoring.py` on purpose -- one implementation
  of that plumbing, used by both PDF-producing tools.
- **Same-run carry-over is implemented as a bucket recomputation, not a
  prompt.** Before each resume is shown to the reviewer,
  `refresh_fit_analysis_with_memory()` re-runs
  `fit_analysis.classify_required_skills()` against the *current* profile
  (memory included). If a required skill moves out of `genuine_gap`, that
  job's resume is re-tailored before review and the move is logged as a
  "round 0" entry in its review log. This is a factual re-lookup, not a
  re-judgment: the five LLM-written fit dimensions are left untouched.
- **Revision cap behavior.** Two revision rounds max, per the assignment.
  If the reviewer still rejects at the cap, the agent does *not* silently
  ship the resume: it asks, inside the same pause, whether the last
  version stands or the job is dropped (a dropped job gets no cover
  letter). No new gate -- it's the same single pause resolving itself.
- **Per-round change logs are preserved.** `tailoring.py` overwrites
  `outputs/<job_id>/change_log.json` on every rework, so each round's log
  is snapshotted into `review_log.json`'s `change_log_shown` field --
  otherwise the "before the rework" state would be unrecoverable and the
  review trail wouldn't be auditable.

## One small change made to an earlier workstream's file

`tailoring.py`'s `_skills_to_add()` gained an optional `profile` argument
(default `None`, so existing calls behave identically). When a skill being
added is memory-learned, its change-log citation is now
`memory.json (stated by candidate, review round N, while reviewing <job>)`
instead of the generic `skill_buckets.evidenced_elsewhere`. Nothing else in
that file changed; the Evidence Rule logic and the four allowed edits are
as the Tailoring workstream left them.

## Files delivered

- `agent/tools/memory_store.py` -- `load_memory()`, `save_memory()`,
  `add_skill()`, `add_other_fact()`, `known_skills()`, `citation_for()`,
  `reset()`. Run `python agent/tools/memory_store.py` to print the current
  memory with provenance.
- `agent/tools/human_review.py` -- the review pause. Public pieces the
  orchestrator should call (each is a natural span boundary for tracing):
  - `format_change_log(job, change_log)` -- what the reviewer sees
  - `extract_facts(comment, profile)` -- the LLM fact/instruction split +
    guard; returns `{skills, other_facts, tailoring_instructions,
    reasoning, rejected}`
  - `write_facts_to_memory(facts, job_id, review_round, comment, profile)`
    -- **wrap this one in the explicit "memory write" span the assignment
    asks for**; it returns one log entry per attempted write
  - `refresh_fit_analysis_with_memory(job, fit_analysis, profile)` -- the
    carry-over step; returns `(fit_analysis, newly_evidenced)`
  - `review_job(...)` -- one resume's full review conversation
  - `run_review_session(top3, profile, input_fn=input, ...)` -- **the whole
    pause; this is the single hard stop to place in the agent loop after
    tailoring and before cover letters.** `top3` is
    `[{"job", "fit_analysis", "tailor_result"}, ...]`.
  - `scripted_input([...])` -- swap in for `input_fn` to replay a canned
    reviewer session (used for the reproducible demo run; the real pause
    defaults to `input`).
- `agent/tools/cover_letter.py` -- `generate_cover_letter(job,
  fit_analysis, profile)`; also `contact_header()` and
  `skills_line_items(fit_analysis, profile)` if the orchestrator wants
  finer spans. Run `python agent/tools/cover_letter.py` to regenerate all
  three letters standalone.
- `scripts/demo_review_script.json` -- the canned reviewer session used for
  the recorded run below.
- `memory/memory.json` -- populated by that run (MLflow, GraphQL).
- Per job, in `outputs/<job_id>/`: `review_log.json` / `review_log.md`,
  `cover_letter.tex`, `cover_letter.pdf`, `cover_letter_log.json` (letter
  text + per-skill citations + the model's own reasoning), and
  `job_details.json`. Plus `outputs/review_session.json` summarising the
  whole pause.

## The recorded end-to-end run (reproducible)

```bash
python agent/tools/memory_store.py            # (optional) inspect memory
python agent/tools/tailoring.py               # fresh baseline tailoring, empty memory
python agent/tools/human_review.py --reset-memory --script scripts/demo_review_script.json
```

What happens, in order:

1. **J18 rejected** with: *"The summary lost the healthcare and
   retail/e-commerce background and reads too generic — keep that domain
   detail and say explicitly that the construction site safety vision work
   is mine. Also add MLflow and GraphQL to my skills…"*
   → `MLflow` and `GraphQL` written to memory with provenance; a
   model-invented fact rejected by the guard; the Tailoring Tool re-run
   with the comment as `revision_feedback`; summary and both bullets
   change. **J18 approved in round 2.**
2. **J21 approved** in round 1 (neither learned skill is in its required
   skills, so nothing to carry over -- correctly, nothing was added).
3. **J14**: `MLflow` *is* in its required skills and had been a
   `genuine_gap`. Before the reviewer saw it, memory moved it to
   `evidenced_elsewhere`, the resume was re-tailored, and
   `outputs/J14/change_log.md` now cites
   `memory.json (stated by candidate, review round 1, while reviewing J18)`
   for it. `Terraform`, `Kubeflow`, `Step Functions` and `CloudFormation`
   stayed genuine gaps and were never added. **J14 approved in round 1.**
4. Three cover letters generated, one per approved job, each verified
   exactly one page. The J21 draft named the genuine gap "query
   understanding"; the no-fabrication check caught it and the correction
   turn removed it (visible in `outputs/J21/cover_letter_log.json`'s
   `evidence_log`).

## What to build next (Orchestrator, Tracing, Full Run, Report/Demo)

- The human pause is **structural, not an LLM decision**: call
  `run_review_session(...)` directly in the loop after all three resumes
  are tailored and before any cover letter. Don't expose it as a tool the
  model can choose to skip.
- Register the Cover Letter Tool as a normal callable tool
  (`generate_cover_letter`), but only for approved jobs -- `run_review_session`
  already returns `approved_job_ids` and calls it for you; if the
  orchestrator prefers to call it itself, pass
  `write_cover_letters=False`.
- Suggested spans: `human_review_pause` (root for the pause) →
  `review_job:<job_id>` → `extract_facts` (LLM), `memory_write` (explicit,
  per the assignment), `tailor_resume:<job_id> (revision N)`, then
  `cover_letter:<job_id>` → its internal LLM call + validation.
- For the traced demo run, use `--script scripts/demo_review_script.json`
  if you want the exact session above, or type the same comment live at
  the console -- both go through identical code.

## Environment notes (Linux workstation used for this workstream)

- This workstream ran on Linux; earlier workstreams were on Mac (Stages
  1-2) and Windows (Stage 3). `pdflatex` came from **TinyTeX** installed
  into the user's home directory (no root needed):
  ```bash
  wget -qO- "https://yihui.org/tinytex/install-bin-unix.sh" | sh
  export PATH="$HOME/.TinyTeX/bin/x86_64-linux:$PATH"
  tlmgr install titlesec enumitem     # the two packages resume.tex needs
  ```
  `tailoring.py`'s `_find_pdflatex()` picks it up from `PATH` (or set
  `PDFLATEX_PATH`).
- LLM: local Ollama with `llama3.2`, exactly as the Foundation workstream
  locked in (`ollama serve` + `ollama pull llama3.2`). No `.env` is
  required -- `llm_client.py`'s defaults already point at
  `http://localhost:11434/v1`.
