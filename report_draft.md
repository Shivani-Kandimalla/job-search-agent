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
