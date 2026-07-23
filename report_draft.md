# Report Draft — Stage 1 contributions (Person 1: Foundation)

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

This gives the Scoring Tool (Stage 2) a healthy, domain-diverse candidate
pool: two Healthcare roles, two Retail/E-commerce roles, two general
Tech/AI roles, and one Construction Technology role — the last of which
lines up directly with the candidate's portfolio-only "Construction Site
Safety Vision Monitor" project, setting up a strong project-swap
demonstration in Stage 3.
