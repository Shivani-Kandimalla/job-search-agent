# Report Draft — Foundation workstream contributions

## Filtering Rules (Section 3.1)

The Filtering Tool (`agent/tools/filtering.py`) is fully deterministic — no
LLM call happens inside it. It applies five rules, in order, and a job is
kept only if it survives all of them. Every rejected job is logged with a
specific, human-readable reason.

1. **Company exclusion** — if the job's company matches (case-insensitive
   substring) any entry in `preferences.companies_to_exclude`, it is
   rejected immediately. Example: `General Motors` and `Teradyne` are
   excluded for this candidate, so J02 and J04 are rejected here.

2. **Target job title match** — the job title's words must be a superset of
   *all* the words in at least one of the candidate's `target_job_titles`
   (after lowercasing and stripping punctuation). This is deliberately
   token-based rather than a strict phrase match, so "Senior AI/ML Engineer"
   still matches the target title "AI Engineer" (both "ai" and "engineer"
   appear as separate tokens once "/" is split on), while "Research
   Scientist" and "AI Product Manager" correctly fail to match any of the
   candidate's target titles (Data Scientist, Machine Learning Engineer,
   Applied Scientist, AI Engineer, NLP Engineer, Applied Data Scientist).

3. **Location preference** — the job's location must match one of the
   candidate's `preferred_locations`, either as a direct substring match
   (e.g. preferred "San Francisco, CA" matches a job located in "San
   Francisco, CA (Remote-friendly)"), a "Remote" keyword match, or a
   state-level fallback match (e.g. preferred "San Francisco, CA" also
   matches "Sunnyvale, CA" because both are in California) — candidates
   usually mean "this general area," not one exact city.

4. **Remote-only filter (optional)** — only applied when
   `preferences.remote_only` is `true`. This candidate has it set to
   `false`, so it does not additionally constrain results (locations were
   already screened in rule 3).

5. **Years of experience** — the job's minimum required years (the first
   integer parsed out of the `years_experience` field, e.g. "5+" → 5, "2-3+"
   → 2) must not exceed the candidate's `years_of_experience` (4). Jobs
   requiring 5+ years are rejected even though they may otherwise be a
   strong domain fit — e.g. J10 (UnitedHealth Group Data Scientist, 5+
   years) and J19 (Senior AI/ML Engineer, 5+ years).

### Result on the real 23-job dataset

- **7 jobs kept**: J01 (OpenAI, ML Eng.), J05 (Amazon, ML Eng. II), J13
  (Flexgen Life Sciences, Data Scientist — Medicare/Medicaid claims), J14
  (Experian Health, MLOps/ML Engineer), J18 (Flexgen Construction Tech, AI
  Engineer — CV/LLMs), J21 (Target, Sr Applied Data Scientist — Search &
  Browse), J22 (Faire, Senior Applied AI/ML Scientist — Retailer Growth).
- **16 jobs rejected**, spanning all five rules — see
  `agent/tools/filtering.py`'s `__main__` output for the full list of
  rejection reasons per job.

This gives the Scoring Tool (built in the Scoring + Fit Analysis workstream)
a healthy, domain-diverse candidate pool: two Healthcare roles, two
Retail/E-commerce roles, two general Tech/AI roles, and one Construction
Technology role — the last of which lines up directly with the candidate's
portfolio-only "Construction Site Safety Vision Monitor" project, setting
up a strong project-swap demonstration in the Resume Tailoring workstream.

---

## Scoring Formula (Section 3.2, first half)

`agent/tools/scoring.py` is fully deterministic — no LLM call. Every one of
the 7 filtered jobs is scored against the candidate's *whole* profile
(resume text + all 7 portfolio projects, not just the 2-3 on the resume +
the 29-item master skills list + any memory-learned facts), not just the
resume page:

```
score = 0.5 * skill_match + 0.3 * experience_alignment + 0.2 * domain_alignment
```

- **skill_match** (weight 0.5, the dominant factor) — fraction of the
  job's `required_skills` that are evidenced *anywhere* in the candidate's
  combined profile text. Matching allows direct substring, a small
  hand-curated synonym table (ML ↔ Machine Learning, RAG ↔
  Retrieval-Augmented Generation, etc.), and a token-overlap fallback for
  multi-word skills. Required-skills strings are split on top-level commas
  only (a custom parser), so a skill like `computer vision (YOLO, Segment
  Anything)` survives as one item instead of being torn apart by the comma
  inside its parentheses.
- **experience_alignment** (weight 0.3) — 1.0 if the candidate's years
  meet or exceed the job's minimum; otherwise decays by 0.25 per year of
  shortfall (floored at 0).
- **domain_alignment** (weight 0.2) — token-overlap between the job's
  `industry_domain` and each of the candidate's portfolio project domains
  (e.g. "Healthcare", "Retail / E-commerce"), taking the best match. A
  job domain that's a superset of a candidate domain (e.g. "Healthcare /
  Predictive Analytics" vs. "Healthcare") scores full credit.

Weights favor skills because they're the most job-specific, concrete
signal; domain gets the smallest weight since it's the coarsest of the
three and location is already a hard filter upstream.

### Top 3 (auto-selected, no human input at this stage)

Run via `python agent/tools/scoring.py`, saved to `outputs/ranked_jobs.json`:

1. **J18** — AI Engineer: Computer Vision, LLMs & ML @ Flexgen Construction
   Technology — score **0.90** (skill=0.80, exp=1.0, domain=1.0)
2. **J21** — Sr Applied Data Scientist, Search & Browse @ Target — score
   **0.86** (skill=0.71, exp=1.0, domain=1.0)
3. **J14** — MLOps Engineer / ML Engineer (Remote) @ Experian Health —
   score **0.77** (skill=0.55, exp=1.0, domain=1.0)

All three are sensible: the candidate meets every job's experience bar
outright (experience_alignment=1.0 across the board) and has a portfolio
project in the exact domain of each posting (Construction Technology,
Retail/E-commerce, Healthcare respectively) even where that project isn't
currently on the resume — exactly the setup the Resume Tailoring
workstream is designed to exploit.

---

## Fit Analysis (Section 3.3)

`agent/tools/fit_analysis.py` makes one LLM call per Top-3 job (local
`llama3.2` via Ollama, JSON-constrained output), and **all five dimensions'
verdicts and text are the model's own output** — Python never decides a
✅/❌ on the model's behalf. This is a deliberate design correction: Section
3.2 explicitly calls Scoring "deterministic; NOT an LLM call," but Section
3.3 never says that about Fit Analysis — it's framed purely as an LLM
narrative task ("Tell me why this job is a good fit for me... Text output
is enough"), so the assignment's "The LLM drives — hard-coded scripts that
execute fixed steps without LLM decision-making will lose points" rule
applies here in full.

What Python *does* do — and this is legitimate tool integration, not
hard-coding a decision — is hand the model accurate **reference facts**
before it reasons:
- Which of the job's required skills are already on the resume, evidenced
  elsewhere in the profile (portfolio-only project / master skills list /
  memory), or a genuine gap nowhere in the candidate's real materials.
- The years-of-experience comparison and the candidate's degree field(s)
  vs. the posting's stated requirement.

The model must use these facts as ground truth (it's told not to
contradict them) but still writes the check/x verdict, the citation, and
the reasoning itself for every one of the five dimensions — Relevant
Experience, Seniority, Education, Core Skills, Projects. That LLM response
is the actual reasoning trace a grader would see, not a Python dict
spliced in afterward.

**Missing-skills two-bucket split** — the reference facts above are
reproduced by the model into `core_skills.missing_evidenced` (safe for the
Tailoring workstream to add to the resume) vs. `core_skills.genuine_gap`
(never to be added, reported honestly instead), matching Section 3.3's own
example format exactly.

**Project-swap Evidence Rule enforcement (fact-check, not judgment
override):** the model can only name a swap project from the real
"portfolio-only" list. If it names something that doesn't exist, the tool
gives it **one self-correction turn** — a second, visible LLM call telling
it exactly which real project names are valid and asking it to fix just
that field — before ever falling back to "no swap." This mirrors the
assignment's own Evidence Rule ("no evidence means no edit") without
overriding the model's actual reasoning about *which* project is the
better fit whenever it names real ones.

### Sample swap recommendation (for the report)

Job **J18** (Flexgen Construction Technology, AI Engineer):
> ✅ Swap Suggestion: replace **"E-commerce Product Recommendation
> Engine"** with **"Construction Site Safety Vision Monitor"**.
> Reasoning: this portfolio-only project aligns more closely with the
> required skills and domain of construction technology than the
> e-commerce recommendation-engine project.

Jobs **J14** and **J21** came back "current projects are already optimal"
in this saved run — a legitimate outcome the model is explicitly allowed
to reach, though it's worth noting the local model is stochastic here:
re-running `fit_analysis.py` can change which job(s) get a swap suggestion
from one run to the next (it has previously surfaced J14 instead of J18
for this same reason — always check the live `outputs/*/fit_analysis.json`
rather than trusting this snippet if you re-run the tool).

Full saved fit analyses for all Top 3 jobs: `outputs/J18/fit_analysis.txt`,
`outputs/J21/fit_analysis.txt`, `outputs/J14/fit_analysis.txt` (plus
`.json` versions for the Tailoring workstream to consume programmatically).

### Known limitation, and a self-correction fix added after final testing

Because every dimension's verdict now genuinely comes from the local 3B
model's own reasoning (as the assignment requires), quality is visibly
less consistent than a fully hard-coded version would be. Final testing
surfaced a concrete case of this: in 2 of the 3 saved runs, the model
marked "Seniority" ❌ for a candidate whose own cited years *met or
exceeded* the posting's stated minimum — e.g. its own text said "candidate
has 4 years, posting requires 3+" and still marked it a fail. That's an
internal self-contradiction, not a defensible close call, since the
system prompt's own rule 6 says "mark x only when they clearly fall
short" and rule 5 explicitly reserves sub-domain-relevance judgment for
"relevant_experience," not "seniority."

`analyze_fit()` now catches this the same way it already catches invalid
project-swap names: a real, visible **self-correction turn** — a second
LLM call quoting the model's own contradictory citation/explanation back
to it, alongside the reference-data years comparison, asking it to
reconcile the two per its own stated rules — before ever falling back to
a disclosed auto-correction. This is a fact-check (is candidate_years ≥
min_years_required, a plain arithmetic comparison already handed to the
model as reference data), not a judgment override: Python never decides
*why* a candidate is or isn't senior enough, it only catches the model
disagreeing with its own arithmetic. Re-verified stable across two
consecutive fresh runs after the fix — zero contradictions in all three
Top-3 jobs both times.

This remains the real, disclosed trade-off of following the assignment's
"LLM drives" rule with a small local model instead of a larger paid one:
the reasoning trace is authentically the model's own, and self-correction
catches outright contradictions, but subtler qualitative judgment calls
(e.g. one run's Education verdict left its citation field blank even
after a retry, falling back to the "(model did not provide a citation)"
placeholder) can still slip through. A larger model (e.g. GPT-4-class)
would likely be materially more consistent here without any code changes,
since the prompt and grounding data would be unchanged — only the
reasoning quality would improve.

---

## Resume Tailoring (Section 3.4)

`agent/tools/tailoring.py` makes exactly **one LLM call per job** (same
local `llama3.2` via Ollama, JSON-constrained output) to write the only
genuinely creative content in this step — the rewritten Professional
Summary, the two rewritten experience bullets, and (if a swap applies) one
resume-style bullet for the swapped-in project. Everything else is decided
deterministically in code, continuing the "LLM proposes, code enforces"
split the Scoring + Fit Analysis workstream established:

- **Which 2 bullets get rewritten** is fixed by the resume template's own
  `AGENT-EDIT-TARGET` markers, not a runtime choice.
- **Which skills get added or highlighted is never asked of the LLM.** It
  is read straight out of the already-deterministic, already fact-checked
  `fit_analysis["skill_buckets"]` from Stage 2: skills in
  `evidenced_elsewhere` get added outright; skills in `on_resume` that
  aren't literally the resume's own wording (a synonym/token-overlap match
  from `scoring.py`, e.g. job says "GenAI/RAG systems," resume only says
  "RAG") get added as a **surface-form alignment** — the exact behavior
  Section 3.4 calls for ("resume says 'ML', job says 'machine learning'").
  Anything in `genuine_gap` is logged, visibly, as *not* applied.
- **The project swap is executed, never re-decided.** Stage 2's
  `project_swap` field was already produced and fact-checked against
  `data/portfolio.txt`; Tailoring just looks the named project up and
  swaps it in.
- **Evidence Rule enforcement on the LLM's prose is a numeric check, not a
  trust call.** Every number in an original bullet (percentages, AUC
  scores, latency, counts) must survive, unchanged, into its rewrite; the
  summary and the swapped project's bullet may only state numbers
  traceable to the real resume/portfolio text. A failed check gets one
  correction turn (a second, visible LLM call), then falls back to the
  original bullet unchanged (or a plain excerpt of the real portfolio
  description for a swap bullet) — the same self-correction pattern
  `fit_analysis.py` already uses for invalid project names and
  self-contradictory seniority verdicts.
- **One-Page Rule**: after every `pdflatex` recompile, `pypdf` verifies the
  PDF is exactly one page. If not, content is trimmed and recompiled in a
  fixed priority order — summary first (least information-dense), then
  the 2 bullets, then the added skills last (cheapest content to lose) —
  capped at 5 attempts. All 3 tailored resumes below compiled to exactly
  one page on the first pass, so this path exists but wasn't exercised in
  the actual run.

### Sample project-swap result (for the report)

Job **J18** (Flexgen Construction Technology, AI Engineer): removed
"E-commerce Product Recommendation Engine" (Retail/E-commerce), added
"Construction Site Safety Vision Monitor" (Construction Technology,
Python/PyTorch/YOLO/OpenCV/edge deployment) — executing Stage 2's
fact-checked swap recommendation. Visually confirmed in
`outputs/J18/resume_after.pdf`: the new project entry matches the
template's exact formatting, the other two on-resume projects are
untouched, and the PDF is still exactly one page.

### Full change logs

Per-job, citation-backed change logs for all three edits (or
"not applied, here's why") plus the project-swap decision:
`outputs/J18/change_log.md`, `outputs/J21/change_log.md`,
`outputs/J14/change_log.md` (JSON versions alongside for the Human Review
workstream to consume programmatically at the review pause).

---

## Human-in-the-Loop Review & Memory (Section 3.5)

The agent stops **exactly once**, after all three resumes have been
tailored and before any cover letter is written. `agent/tools/human_review.py`
implements that pause; there is no other human gate anywhere in the
pipeline.

### What the reviewer sees and does

For each of the Top 3 resumes, in ranked order, the console prints the full
citation-backed change log — every edit as a `BEFORE` / `AFTER` pair with
its `CITATION` and `REASON`, including the project swap and including the
edits that were **considered and refused** (each genuine-gap skill is
printed as `skills (not applied)` with the reason it was not added). The
reviewer then types `approve`, or `reject` plus free-text comments.

On a rejection the agent does three things, in this order:

1. **Extracts candidate facts from the comment** (one LLM call). Review
   comments mix two different kinds of content, and only one of them
   belongs in permanent memory: *facts about the candidate* ("add MLflow
   and GraphQL, I've used both") versus *instructions about this one edit*
   ("the summary is too generic"). The model performs the split; a
   code-level guard then discards any "extracted" skill whose text does not
   literally appear in the reviewer's own comment, so a model that
   pattern-matches the job posting cannot write a skill into memory that
   the candidate never claimed.
2. **Writes the surviving facts to `memory/memory.json`** with provenance,
   and reloads the profile from disk so every later tool call sees them.
3. **Re-runs the Tailoring Tool** with the comment passed through as
   `revision_feedback`, capped at **2 revision rounds**. Each round logs
   `{round, decision, feedback, facts_learned, actions_taken}` to
   `outputs/<job_id>/review_log.{json,md}`, and stores a copy of the change
   log exactly as it was shown that round (`change_log_shown`) -- tailoring
   overwrites `change_log.json` on every rework, so without that copy the
   earlier rounds' edits would not be auditable afterwards.

Only after approval does the pipeline continue to the Cover Letter Tool.
A resume that is still rejected after the 2-round cap is not silently
shipped: the reviewer is asked, within the same pause, whether the last
version stands or the job is dropped (a dropped job gets no cover letter).

### Memory file schema

```json
{
  "skills_learned": [
    {
      "skill": "MLflow",
      "source": "stated by candidate",
      "review_round": 1,
      "job_id": "J18",
      "comment": "<the verbatim reviewer comment the fact came from>",
      "timestamp": "2026-07-25T19:58:04"
    }
  ],
  "other_facts": []
}
```

`memory/memory.json` is loaded at startup by `profile.load_full_profile()`,
so remembered skills count as evidence in the Scoring Tool, the Fit
Analysis Tool, the Tailoring Tool and the Cover Letter Tool on **every
later run**, not just the run that learned them. Scope is limited to skills
and candidate facts, per the assignment; tailoring instructions are never
written to memory.

### One full human review round (from the recorded end-to-end run)

**Job J18 — AI Engineer: Computer Vision, LLMs & ML @ Flexgen Construction
Technology. Round 1: REJECTED.**

> **Feedback given:** "The summary lost the healthcare and retail/e-commerce
> background and reads too generic — keep that domain detail and say
> explicitly that the construction site safety vision work is mine. Also add
> MLflow and GraphQL to my skills: I have used MLflow for experiment
> tracking at work and GraphQL on a side project, they are just missing from
> my skills list."

Actions the agent took and logged (`outputs/J18/review_log.md`):

- `MEMORY WRITE: remembered skill 'MLflow' (stated by candidate, review round 1, job J18)`
- `MEMORY WRITE: remembered skill 'GraphQL' (stated by candidate, review round 1, job J18)`
- `MEMORY REJECTED: proposed other_fact "I'm open to hybrid roles in Seattle" — not supported by the reviewer's comment` *(the guard firing on a fact the model invented; it never reached the memory file)*
- `Re-ran the Tailoring Tool with the reviewer's comment as revision feedback; sections that changed: experience-bullet-1, experience-bullet-2, summary.`

The reworked summary (round 1 as shown to the reviewer → round 2 after the
rework; both rounds are preserved verbatim in
`outputs/J18/review_log.json`'s `change_log_shown` field):

> *Round 1 (rejected):* "Results-driven AI engineer with a Master's degree
> in Data Science, seeking to leverage expertise in machine learning and
> computer vision to drive innovation in construction technology."
>
> *Round 2 (after rework):* "As a seasoned Data Scientist with experience
> in predictive risk modeling, recommendation systems, and
> retrieval-augmented generation, I leverage my strong Python foundation to
> tackle complex problems in healthcare and retail/e-commerce. Most
> recently, I developed a computer-vision pipeline that analyzes job-site
> camera photos to detect personal protective equipment (PPE) violations,
> utilizing fine-tuned YOLO object detection for edge deployment on
> low-connectivity sites."

Both of the reviewer's tailoring instructions landed: the healthcare and
retail/e-commerce domain detail is back, and the construction site safety
vision work is now stated as the candidate's own (grounded in the
"Construction Site Safety Vision Monitor" portfolio project that the same
job's project swap had already put on the resume).

**Round 2: APPROVED.**

### One memory example (comment → memory entry → reuse)

The same comment taught the agent **MLflow**, a skill that is deliberately
absent from `data/persona_preferences.json`'s master skills list. Its reuse
is visible two jobs later in the *same* run, with no repetition from the
reviewer:

- J14 (Experian Health, MLOps Engineer) lists `MLflow` in its required
  skills. Before the review pause it sat in that job's `genuine_gap`
  bucket, so the Tailoring Tool was forbidden from adding it.
- Before J14's resume was shown to the reviewer, the agent recomputed that
  job's deterministic skill buckets against the *current* memory
  (`refresh_fit_analysis_with_memory`). `MLflow` moved
  `genuine_gap → evidenced_elsewhere`, and the resume was re-tailored.
- `outputs/J14/change_log.md` now contains:

  ```
  ## skills
  - Before: (not listed)
  - After: MLflow
  - Citation: memory.json (stated by candidate, review round 1, while reviewing J18)
  ```

  and the compiled `outputs/J14/resume_after.pdf` carries
  `Additional (aligned with this role): Lambda, MLflow, TensorFlow Serving`.
- `outputs/J14/review_log.md` records the carry-over as a "round 0" entry,
  so it is auditable that the change happened *before* any reviewer input
  on that job.

**Terraform, Kubeflow, Step Functions and CloudFormation stay in J14's
`genuine_gap` bucket and never reach the resume** — the candidate never
claimed them, so the agent never adds them. That contrast (MLflow added,
Terraform refused) is the Evidence Rule and the memory feature working
together.

## Cover Letter Tool (Section 3.6)

`agent/tools/cover_letter.py` runs once per **approved** job and produces a
one-page PDF at `outputs/<job_id>/cover_letter.pdf`.

**Tooling choice:** the letter is authored as LaTeX and compiled with the
same `pdflatex` toolchain the resume already requires (rather than adding a
separate Python PDF library). That means zero new dependencies for a
grader, a letter that visually matches the resume, and the same
`pypdf`-based one-page verification used by the Tailoring Tool. The
compile / page-count / LaTeX-escaping helpers are imported from
`tailoring.py`, so there is a single implementation of that plumbing.

**Structure** (all six elements the assignment lists): contact header
parsed straight out of `resume/resume.tex` (so the letter and resume can
never disagree about the candidate's details) → date → company block →
greeting → an opening naming the exact role and company with a hook taken
from that job's `Company Details` CSV field → one or two body paragraphs
mapping real resume/portfolio experience onto the job description → a
skills line → closing.

**No-fabrication enforcement** mirrors the tailoring step — the LLM writes
prose, code decides what may be claimed:

- The **skills line is not written by the model.** It is built from the
  deterministic `skill_buckets` (on-resume + evidenced-elsewhere, which
  includes memory-learned skills), each item carrying its own citation in
  `outputs/<job_id>/cover_letter_log.json`.
- **Genuine-gap skills are forbidden phrases.** If any appears anywhere in
  the generated prose — even while describing what the company does — the
  draft is rejected, the model gets one correction turn, and a
  deterministic fallback letter (assembled only from the job posting's own
  Company Details, the resume's own Professional Summary, and the featured
  portfolio project) is used if it still fails. In the recorded run this
  fired once: the J21 draft used the phrase "query understanding" (a
  genuine gap for this candidate) and the correction turn removed it.
- Every **number** in the prose must be traceable to the real resume or
  portfolio text (the same `_no_new_numbers` check the resume tool uses).
- The **role title, company name and contact details are inserted by the
  template**, not restated by the model.
- **One-Page Rule**: page count is verified with `pypdf` after each
  compile; if it overflows, the second body paragraph is dropped first,
  then the first is shortened, then the opening — the skills line and the
  closing are required elements and are never dropped. All three letters in
  the recorded run compiled to exactly one page.

### Reproducing the recorded review + cover letter run

```bash
python agent/tools/human_review.py --reset-memory                            # interactive
python agent/tools/human_review.py --reset-memory --script scripts/demo_review_script.json
```

The second form replays the exact reviewer session written up above
(reject J18 with the MLflow/GraphQL comment, then approve all three), which
is what produced every artifact quoted in this section.
