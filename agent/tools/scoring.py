"""
Scoring Tool (Section 3.2 of the assignment).

Fully deterministic -- this NEVER calls an LLM. The agent invokes this as a
tool and receives a plain number back; the model does not generate the
score itself.

Formula (weights chosen and documented in report_draft.md):

    score = 0.5 * skill_match + 0.3 * experience_alignment + 0.2 * domain_alignment

Each job is scored against the WHOLE profile: resume text, every portfolio
project (not just the 2-3 on the resume), the master skills list, and any
facts already written to memory (e.g. a skill the candidate mentioned
during a review pause) -- not just what's printed on the resume page.

Location is intentionally excluded from the score (per spec, "location
optional") since it's already a hard filter in the Filtering Tool.
"""

import re

from profile import (
    load_full_profile,
    load_persona_preferences,
    split_skills,
)
from filtering import filter_jobs, load_jobs

# A handful of common AI/ML surface-form synonyms so "ML" on the resume
# still counts as matching "Machine Learning" in a job posting, etc.
# This is intentionally small and hand-curated, not a general NLP model --
# the Tailoring Tool (a later workstream) reuses this exact map for its
# surface-form keyword alignment step, so keep the two in sync.
SKILL_SYNONYMS = {
    "ml": ["machine learning"],
    "machine learning": ["ml"],
    "nlp": ["natural language processing"],
    "natural language processing": ["nlp"],
    "cv": ["computer vision"],
    "computer vision": ["cv"],
    "genai": ["generative ai"],
    "generative ai": ["genai"],
    "llm": ["large language model", "large language models"],
    "large language models": ["llm"],
    "large language model": ["llm"],
    "llms": ["large language model", "large language models"],
    "rag": ["retrieval-augmented generation", "retrieval augmented generation"],
    "retrieval-augmented generation": ["rag"],
    "aws": ["amazon web services"],
    "gcp": ["google cloud", "google cloud platform"],
    "ci/cd": ["continuous integration", "github actions", "continuous deployment"],
    "a/b testing": ["ab testing", "experimentation"],
}


def _tokenize(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _skill_present(skill: str, candidate_text_lower: str) -> bool:
    """Is this required skill evidenced anywhere in the candidate's combined
    profile text? Tries: direct substring, known synonym substring, then a
    token-overlap fallback for multi-word skills (e.g. 'vector databases'
    matches text containing 'vector database')."""
    skill_lower = skill.strip().lower()
    if not skill_lower:
        return False

    if skill_lower in candidate_text_lower:
        return True

    for alt in SKILL_SYNONYMS.get(skill_lower, []):
        if alt in candidate_text_lower:
            return True

    tokens = [t for t in re.findall(r"[a-z0-9]+", skill_lower) if len(t) > 2]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in candidate_text_lower)
    return (hits / len(tokens)) >= 0.6


def _min_years_required(years_experience_str: str) -> int:
    match = re.search(r"\d+", years_experience_str or "")
    return int(match.group()) if match else 0


def _experience_alignment(candidate_years: int, min_years_required: int) -> float:
    if candidate_years >= min_years_required:
        return 1.0
    gap = min_years_required - candidate_years
    return max(0.0, 1.0 - 0.25 * gap)


def _domain_overlap(tokens_a: set, tokens_b: set) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    shorter = min(len(tokens_a), len(tokens_b))
    inter = len(tokens_a & tokens_b)
    return inter / shorter if shorter else 0.0


def _domain_alignment(job_domain: str, candidate_domains: list) -> float:
    job_tokens = _tokenize(job_domain)
    if not candidate_domains:
        return 0.0
    return max(_domain_overlap(job_tokens, _tokenize(d)) for d in candidate_domains)


def build_candidate_skill_text(profile: dict) -> str:
    """Everything the candidate 'knows' or has evidence of, concatenated
    into one lowercase blob for substring/token matching: resume + every
    portfolio project (not just on-resume ones) + master skills list +
    memory-learned skills."""
    parts = [
        profile["resume_text"],
        profile["portfolio_text"],
        " ".join(profile["master_skills"]),
        " ".join(profile["memory_skills"]),
    ]
    return " ".join(parts).lower()


def score_job(job: dict, profile: dict) -> dict:
    """
    job: a dict (one row from data/jobs.csv)
    profile: the dict returned by profile.load_full_profile()

    Returns a breakdown dict:
      {
        "job_id", "score",
        "skill_match", "experience_alignment", "domain_alignment",
        "matched_skills", "missing_skills",
        "min_years_required", "candidate_years",
      }
    """
    candidate_text = build_candidate_skill_text(profile)
    required_skills = split_skills(job["required_skills"])

    matched, missing = [], []
    for skill in required_skills:
        if _skill_present(skill, candidate_text):
            matched.append(skill)
        else:
            missing.append(skill)

    skill_match = len(matched) / len(required_skills) if required_skills else 0.0

    min_years_required = _min_years_required(job["years_experience"])
    experience_alignment = _experience_alignment(profile["candidate_years"], min_years_required)

    candidate_domains = [p["domain"] for p in profile["portfolio_projects"]]
    domain_alignment = _domain_alignment(job["industry_domain"], candidate_domains)

    score = 0.5 * skill_match + 0.3 * experience_alignment + 0.2 * domain_alignment

    return {
        "job_id": job["job_id"],
        "title": job["title"],
        "company": job["company"],
        "score": round(score, 4),
        "skill_match": round(skill_match, 4),
        "experience_alignment": round(experience_alignment, 4),
        "domain_alignment": round(domain_alignment, 4),
        "matched_skills": matched,
        "missing_skills": missing,
        "min_years_required": min_years_required,
        "candidate_years": profile["candidate_years"],
    }


def score_and_rank(jobs: list, profile: dict) -> list:
    """Scores every job, returns them sorted best-first."""
    scored = [score_job(job, profile) for job in jobs]
    return sorted(scored, key=lambda s: s["score"], reverse=True)


def top_n(jobs: list, profile: dict, n: int = 3) -> list:
    return score_and_rank(jobs, profile)[:n]


if __name__ == "__main__":
    import json
    import os

    base = os.path.join(os.path.dirname(__file__), "..", "..")
    all_jobs = load_jobs(os.path.join(base, "data", "jobs.csv"))
    preferences = load_persona_preferences()["preferences"]
    kept, _rejected = filter_jobs(all_jobs, preferences)

    profile = load_full_profile()

    ranked = score_and_rank(kept, profile)

    print(f"Scored {len(ranked)} filtered jobs against the whole profile "
          f"(resume + {len(profile['portfolio_projects'])} portfolio projects + "
          f"{len(profile['master_skills'])} master skills + "
          f"{len(profile['memory_skills'])} memory-learned skills):\n")

    for i, r in enumerate(ranked, 1):
        marker = "  <-- TOP 3" if i <= 3 else ""
        print(f"{i}. [{r['job_id']}] {r['title']} @ {r['company']} "
              f"-> score={r['score']} "
              f"(skill={r['skill_match']}, exp={r['experience_alignment']}, "
              f"domain={r['domain_alignment']}){marker}")
        print(f"     matched skills:  {r['matched_skills']}")
        print(f"     missing skills:  {r['missing_skills']}")

    outputs_dir = os.path.join(base, "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    with open(os.path.join(outputs_dir, "ranked_jobs.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"ranked": ranked, "top3_job_ids": [r["job_id"] for r in ranked[:3]]},
            f,
            indent=2,
        )
    print(f"\nSaved full ranking to outputs/ranked_jobs.json")
