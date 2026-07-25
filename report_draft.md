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

## Fit Analysis (Section 3.2, second half)

`agent/tools/fit_analysis.py` makes one LLM call per Top-3 job (local
`llama3.2` via Ollama, JSON-constrained output). To keep a small local
model from hallucinating, the analysis is split by how *objective* each
dimension is:

- **Computed in Python (no LLM judgment involved):** Seniority (years
  comparison), Education (keyword match between the candidate's degree
  field(s), parsed straight out of the resume, and the posting's stated
  requirement — defaults to a pass if the posting doesn't specify a field,
  or says "...or related field"), and Core Skills (the same skill-bucket
  split described below, thresholded at 50% coverage).
- **Left to the LLM, because it genuinely requires judgment:** Relevant
  Experience (is the *nature* of the candidate's past work relevant to
  this role, independent of years) and Projects (do the on-resume projects
  read as a fit), plus the project-swap recommendation and overall
  summary.

Every dimension still ends up with a status (✅/❌) and a citation into the
real resume/portfolio/job text — the assignment's 5-dimension, "cite
something real" requirement is satisfied either way.

**Missing-skills two-bucket split** (computed once, shared verbatim with
the LLM so it can't contradict it):

- **evidenced elsewhere** — a required skill not literally on the resume,
  but real: it shows up in a portfolio-only project, the master skills
  list, or a memory-learned fact. Safe for the Tailoring workstream to add
  to the resume.
- **genuine gap** — not evidenced anywhere in the candidate's actual
  materials. Must never be added; reported honestly instead.

**Project-swap Evidence Rule enforcement:** the LLM is only allowed to
recommend swapping in a project from the real "portfolio-only" list, never
an invented one. Rather than trust the model's own `recommended` boolean
(it occasionally set `false` while its reasoning text still argued for a
swap), the code re-derives `recommended` from whether both project names
it returned exactly match a real project — if they don't, the suggestion
is discarded and replaced with an honest "current projects are already
optimal" fallback, regardless of what the model claimed.

### Sample swap recommendation (for the report)

Job **J21** (Target, Sr Applied Data Scientist — Search & Browse):
> Swap recommended: replace **"E-commerce Product Recommendation Engine"**
> with **"Demand Forecasting for Retail Supply Chain"**.
> Reasoning: the candidate's existing recommendation-engine project doesn't
> address the posting's search-ranking/retrieval focus; the demand
> forecasting project demonstrates the same Retail/E-commerce domain via
> different, still-relevant technical depth (time-series forecasting,
> large-scale data pipelines).

A second validated swap example, job **J14** (Experian Health, MLOps
Engineer): replace **"Patient Readmission Risk Predictor"** with
**"Medical Imaging Anomaly Detector"** — both are Healthcare-domain
projects, but the posting's AWS/MLOps-pipeline focus made the tailoring
team want a different real project than the default resume pick. Job
**J18** came back "current projects are already optimal" (a legitimate,
non-swap outcome — the resume's existing skills already cover 80% of the
posting's needs).

Full saved fit analyses for all Top 3 jobs: `outputs/J18/fit_analysis.txt`,
`outputs/J21/fit_analysis.txt`, `outputs/J14/fit_analysis.txt` (plus
`.json` versions for the Tailoring workstream to consume programmatically).

### Known limitation (candidate for the report's ethics/honesty reflection)

Even with JSON-constrained output and a deterministic core, the local 3B
model occasionally writes free-text reasoning that slightly overstates a
project's fit (e.g. attributing a tech-stack item to a project that
doesn't list it) — a real illustration of why the Evidence Rule is
enforced in *code*, not just prompted for: a small model can't be fully
trusted to self-police factual grounding in prose, so anything that feeds
a structured decision (skill buckets, swap validity, seniority, education)
is computed outside the model, and only genuinely qualitative narrative is
left to it.
