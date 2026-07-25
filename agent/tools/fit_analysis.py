"""
Fit Analysis Tool (Section 3.2 of the assignment, second half).

One LLM call per Top-3 job. Unlike scoring.py, this DOES call the model --
but the risky, fact-sensitive part (which required skills are actually
evidenced somewhere in the candidate's real materials) is computed
deterministically in Python first and handed to the model as ground truth.
The model's job is narrower and more qualitative: write the Relevant
Experience / Seniority / Education / Projects narrative, and recommend a
project swap (or say the current ones are already optimal). This division
of labor is what keeps a small local model (llama3.2) from hallucinating
skills that don't exist in the profile.

Enforces (per PLAN.md):
  - All 5 dimensions in the output: Relevant Experience, Seniority,
    Education, Core Skills, Projects -- each with a real citation.
  - The two-bucket missing-skills split: evidenced-elsewhere (usable by
    the Tailoring workstream) vs. genuine gap (never to be added).
  - An explicit project-swap recommendation, or an explicit statement that
    current projects are already optimal.
"""

import json
import re

from llm_client import chat
from profile import load_full_profile, split_skills
from scoring import _skill_present, score_job


def classify_required_skills(job: dict, profile: dict) -> dict:
    """Splits a job's required_skills into 3 deterministic buckets, by
    checking two separate text blobs (resume-only vs. rest-of-profile):

      on_resume          -> already literally on the resume
      evidenced_elsewhere -> not on the resume, but real (portfolio-only
                              project, master skills list, or a
                              memory-learned fact) -- Tailoring MAY surface
                              these on the resume, since they're truthful
      genuine_gap        -> not evidenced anywhere in the candidate's
                             actual materials -- must NEVER be added
    """
    resume_lower = profile["resume_text"].lower()
    rest_lower = " ".join([
        profile["portfolio_text"],
        " ".join(profile["master_skills"]),
        " ".join(profile["memory_skills"]),
    ]).lower()

    required_skills = split_skills(job["required_skills"])

    on_resume, evidenced_elsewhere, genuine_gap = [], [], []
    for skill in required_skills:
        if _skill_present(skill, resume_lower):
            on_resume.append(skill)
        elif _skill_present(skill, rest_lower):
            evidenced_elsewhere.append(skill)
        else:
            genuine_gap.append(skill)

    return {
        "on_resume": on_resume,
        "evidenced_elsewhere": evidenced_elsewhere,
        "genuine_gap": genuine_gap,
    }


def compute_seniority_dimension(job: dict, profile: dict, score_breakdown: dict) -> dict:
    """Seniority is just years-of-experience arithmetic -- there's no
    judgment call here, so compute it in Python instead of trusting a
    small local model to not flip check/x on a simple >=/< comparison."""
    candidate_years = profile["candidate_years"]
    min_years = score_breakdown["min_years_required"]
    meets = candidate_years >= min_years
    return {
        "status": "check" if meets else "x",
        "citation": f"Candidate has {candidate_years} years of experience "
                    f"(persona_preferences.json); posting lists "
                    f"'{job['years_experience']}' ({min_years}+ years required).",
        "explanation": (
            f"Meets the seniority bar: {candidate_years} years >= {min_years}+ required."
            if meets else
            f"Falls short of the seniority bar: {candidate_years} years < {min_years}+ required."
        ),
    }


def compute_core_skills_dimension(skill_buckets: dict, score_breakdown: dict) -> dict:
    """Deterministic pass/fail on skill_match, using the exact same
    matched/missing computation as scoring.py so this dimension can never
    contradict the score the job was ranked by."""
    meets = score_breakdown["skill_match"] >= 0.5
    on_resume = skill_buckets["on_resume"]
    elsewhere = skill_buckets["evidenced_elsewhere"]
    gap = skill_buckets["genuine_gap"]
    citation = (
        f"On resume: {', '.join(on_resume) or '(none)'}. "
        f"Evidenced elsewhere in profile: {', '.join(elsewhere) or '(none)'}. "
        f"Genuine gaps: {', '.join(gap) or '(none)'}."
    )
    return {
        "status": "check" if meets else "x",
        "citation": citation,
        "explanation": (
            f"{score_breakdown['skill_match'] * 100:.0f}% of required skills are "
            f"evidenced somewhere in the candidate's real profile "
            f"({'meets' if meets else 'below'} the 50% bar)."
        ),
    }


def _validate_project_swap(swap: dict, on_resume_names: list, portfolio_only_names: list) -> dict:
    """Evidence Rule enforcement: a swap is only ever accepted if BOTH
    project names exactly match a real project in the portfolio file. This
    also repairs the model's occasional recommended=false/true vs.
    populated-fields inconsistency -- the presence of two verifiable names
    is what determines "recommended", not the model's own boolean."""
    swap = swap or {}
    weak = (swap.get("weak_resume_project") or "").strip().lower()
    better = (swap.get("better_portfolio_project") or "").strip().lower()

    weak_match = next((n for n in on_resume_names if n.lower() == weak), None)
    better_match = next((n for n in portfolio_only_names if n.lower() == better), None)

    if weak_match and better_match:
        return {
            "recommended": True,
            "weak_resume_project": weak_match,
            "better_portfolio_project": better_match,
            "reasoning": swap.get("reasoning") or "",
        }

    if not weak and not better:
        # Model made a clean, deliberate "already optimal" call without
        # naming any project -- its reasoning is safe to keep verbatim.
        return {
            "recommended": False,
            "weak_resume_project": None,
            "better_portfolio_project": None,
            "reasoning": swap.get("reasoning") or "Current on-resume projects are retained as already optimal.",
        }

    # The model named at least one project but the pairing didn't fully
    # verify against the real portfolio -- drop its reasoning rather than
    # keep text that may still argue for a swap while recommended=False,
    # which would read as self-contradictory (and risks citing a project
    # detail that doesn't actually exist, violating the Evidence Rule).
    return {
        "recommended": False,
        "weak_resume_project": None,
        "better_portfolio_project": None,
        "reasoning": "Current on-resume projects are retained as already optimal "
                     "(the model's suggested swap did not name two verifiable, "
                     "existing projects, so it was discarded per the Evidence Rule).",
    }


def compute_education_dimension(job: dict, profile: dict) -> dict:
    """Whether the candidate's degree(s) satisfy the posting's education
    ask, if it states one. Keyword-matched against the job description
    rather than left to the LLM, since a small local model kept
    incorrectly flagging 'M.S. in Data Science' as not satisfying a
    posting that literally asks for '...Data Science, or related field'."""
    degree_fields = profile["degree_fields"]
    degree_summary = ", ".join(degree_fields) if degree_fields else "no degree listed on resume"
    text = (job.get("description", "") + " " + job.get("title", "")).lower()

    mentions_requirement = any(kw in text for kw in ("degree", "bachelor", "master", "b.s.", "m.s.", "phd", "ph.d"))
    if not mentions_requirement:
        return {
            "status": "check",
            "citation": f"Posting does not state a specific degree requirement; candidate holds: {degree_summary}.",
            "explanation": "No education requirement was stated in the posting, so the candidate's degree(s) are not a blocker.",
        }

    if "related field" in text:
        return {
            "status": "check",
            "citation": f"Posting accepts a degree '...or related field'; candidate holds: {degree_summary}.",
            "explanation": "The posting's open-ended 'or related field' language is satisfied by the candidate's quantitative degree(s).",
        }

    field_match = next(
        (field for field in degree_fields if any(
            word in text for word in field.lower().split() if len(word) > 3
        )),
        None,
    )
    if field_match:
        return {
            "status": "check",
            "citation": f"Candidate's '{field_match}' degree matches a field named in the posting's requirements.",
            "explanation": "The candidate's degree field is explicitly named in the posting's qualifications.",
        }

    requirement_match = re.search(r"[^.]*degree[^.]*\.", text)
    requirement_text = requirement_match.group().strip() if requirement_match else "a specific degree field"
    return {
        "status": "x",
        "citation": f"Posting requirement: \"{requirement_text}\"; candidate holds: {degree_summary}.",
        "explanation": "The candidate's degree field(s) don't textually match the specific field(s) named in the posting.",
    }


def _format_projects(projects: list) -> str:
    lines = []
    for p in projects:
        tag = "ON RESUME" if p["on_resume"] else "PORTFOLIO ONLY (not on resume)"
        lines.append(
            f"- \"{p['name']}\" [{tag}] | Domain: {p['domain']} | "
            f"Tech: {', '.join(p['tech_stack'])} | {p['description']}"
        )
    return "\n".join(lines)


SYSTEM_PROMPT = """You are a meticulous, honest fit-analysis assistant inside a job search \
agent. You compare ONE job posting against ONE candidate's real profile \
(resume + full project portfolio + master skills list + memory facts).

Three of the five fit dimensions -- Seniority, Education, and Core Skills \
-- are computed for you deterministically (given below as DETERMINISTIC \
ANALYSIS). Do not recompute or contradict them. Your job is the two \
dimensions that require real judgment: Relevant Experience and Projects, \
plus the project-swap recommendation and overall summary.

Hard rules, no exceptions:
1. Every claim you make must be traceable to something literally present in \
the CANDIDATE PROFILE given to you below. Never invent a skill, project, \
job title, or achievement.
2. The "evidenced_elsewhere" and "genuine_gap" skill lists given to you are \
already correct and final -- do not move skills between buckets or add new \
ones.
3. For the project recommendation: you may only recommend swapping in a \
project from the "PORTFOLIO ONLY" list below (never invent one), or \
explicitly say the current on-resume projects are already optimal.
4. Output ONLY a single valid JSON object. No markdown code fences, no \
commentary before or after, no trailing commas.
5. "citation" fields must NEVER be left empty -- always quote or closely \
paraphrase the specific resume line, portfolio entry, or job-posting detail \
that backs your status/explanation for that dimension.
6. Status semantics -- mark "check" only when the candidate meets or \
exceeds the job's bar for that dimension. Mark "x" only when the candidate \
clearly falls short of what the posting asks for.
7. "relevant_experience" is about the NATURE and DOMAIN of the candidate's \
past work (what they built, which industry, which responsibilities) --  \
it is NOT about years of experience (Seniority already covers years and \
is resolved above). Having MORE years than required is never a reason to \
mark this "x"; only mark "x" if the actual work described doesn't relate \
to what this posting needs.

Respond with EXACTLY this JSON shape (fill in every field):
{
  "relevant_experience": {"status": "check" or "x", "citation": "<verbatim or near-verbatim resume/portfolio detail>", "explanation": "<1-2 sentences>"},
  "projects": {"status": "check" or "x", "citation": "<detail>", "explanation": "<1-2 sentences>"},
  "project_swap": {
    "recommended": true or false,
    "weak_resume_project": "<exact project name from ON RESUME list, or null>",
    "better_portfolio_project": "<exact project name from PORTFOLIO ONLY list, or null>",
    "reasoning": "<1-3 sentences, cite the job's domain/skills and the project's domain/tech>"
  },
  "overall_summary": "<2-3 sentence honest overall fit summary>"
}"""


def _build_user_prompt(job: dict, profile: dict, skill_buckets: dict, score_breakdown: dict) -> str:
    on_resume_projects = [p for p in profile["portfolio_projects"] if p["on_resume"]]
    portfolio_only_projects = [p for p in profile["portfolio_projects"] if not p["on_resume"]]

    return f"""JOB POSTING
Title: {job['title']}
Company: {job['company']}
Domain: {job['industry_domain']}
Location: {job['location']}
Required skills: {job['required_skills']}
Years of experience required: {job['years_experience']}
Description: {job['description']}

CANDIDATE PROFILE

Resume (plain text):
{profile['resume_plaintext']}

ON RESUME projects (already on the resume):
{_format_projects(on_resume_projects)}

PORTFOLIO ONLY projects (real, exist in the candidate's history, NOT currently on the resume -- these are your ONLY allowed swap-in candidates):
{_format_projects(portfolio_only_projects)}

Master skills list: {', '.join(profile['master_skills'])}
Memory-learned facts (skills confirmed by the candidate after the resume was written): {', '.join(profile['memory_skills']) or '(none yet)'}
Candidate years of experience: {profile['candidate_years']}

DETERMINISTIC ANALYSIS (already computed, do not recompute or contradict):
- Required skills already on resume: {', '.join(skill_buckets['on_resume']) or '(none)'}
- Required skills evidenced elsewhere in profile (portfolio/master-skills/memory, but NOT yet on resume -- tailoring MAY add these): {', '.join(skill_buckets['evidenced_elsewhere']) or '(none)'}
- Required skills that are a genuine gap (not evidenced anywhere -- NEVER add these): {', '.join(skill_buckets['genuine_gap']) or '(none)'}
- Candidate years of experience {profile['candidate_years']} vs. posting's required {score_breakdown['min_years_required']}+ -> Seniority dimension already resolved.
- Candidate degree field(s) {', '.join(profile['degree_fields']) or '(none)'} vs. posting's stated requirement -> Education dimension already resolved.
- Overall deterministic score: {score_breakdown['score']} (skill_match={score_breakdown['skill_match']}, experience_alignment={score_breakdown['experience_alignment']}, domain_alignment={score_breakdown['domain_alignment']})

Now produce the JSON fit analysis described in your instructions."""


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in model output:\n{raw}")
    candidate = raw[start:end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Small local models frequently emit trailing commas or stray commas
    # before a closing brace/bracket -- repair the common cases and retry
    # once before giving up.
    repaired = re.sub(r",(\s*[}\]])", r"\1", candidate)
    return json.loads(repaired)


def analyze_fit(job: dict, profile: dict, score_breakdown: dict = None, retries: int = 2) -> dict:
    """Returns the structured fit-analysis dict for one job, with the
    deterministic skill_buckets and score merged in (so downstream tools
    -- Tailoring -- get everything from one object)."""
    skill_buckets = classify_required_skills(job, profile)
    score_breakdown = score_breakdown or score_job(job, profile)
    user_prompt = _build_user_prompt(job, profile, skill_buckets, score_breakdown)

    def _is_blank(entry: dict) -> bool:
        entry = entry or {}
        return not (entry.get("citation") or "").strip() and not (entry.get("explanation") or "").strip()

    last_error = None
    parsed = None
    for attempt in range(retries + 1):
        raw = chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            # Slightly higher temperature on retries so a re-ask isn't just
            # a coin-flip repeat of the same blank/low-quality response.
            temperature=0.2 if attempt == 0 else 0.4,
            response_format={"type": "json_object"},
        )
        try:
            candidate = _extract_json(raw)
        except (ValueError, json.JSONDecodeError) as e:
            last_error = e
            continue

        parsed = candidate
        is_last_attempt = attempt == retries
        both_blank = _is_blank(candidate.get("relevant_experience")) and _is_blank(candidate.get("projects"))
        if not both_blank or is_last_attempt:
            break
        # Both judgment dimensions came back empty -- worth one more try
        # before falling back to placeholder text.

    if parsed is None:
        raise RuntimeError(
            f"Model failed to return valid JSON after {retries + 1} attempts. "
            f"Last error: {last_error}"
        )

    for dim in ("relevant_experience", "projects"):
        entry = parsed.get(dim) or {}
        if not entry.get("citation"):
            entry["citation"] = "(model did not provide a citation for this dimension)"
        if not entry.get("explanation"):
            entry["explanation"] = "(model did not provide an explanation for this dimension)"
        if entry.get("status") not in ("check", "x"):
            entry["status"] = "x"
        parsed[dim] = entry

    parsed["seniority"] = compute_seniority_dimension(job, profile, score_breakdown)
    parsed["education"] = compute_education_dimension(job, profile)
    parsed["core_skills"] = compute_core_skills_dimension(skill_buckets, score_breakdown)

    on_resume_names = [p["name"] for p in profile["portfolio_projects"] if p["on_resume"]]
    portfolio_only_names = [p["name"] for p in profile["portfolio_projects"] if not p["on_resume"]]
    parsed["project_swap"] = _validate_project_swap(
        parsed.get("project_swap"), on_resume_names, portfolio_only_names
    )

    parsed["job_id"] = job["job_id"]
    parsed["title"] = job["title"]
    parsed["company"] = job["company"]
    parsed["skill_buckets"] = skill_buckets
    parsed["score_breakdown"] = score_breakdown
    return parsed


def format_report(analysis: dict) -> str:
    """Renders the structured analysis as the human-readable
    check/x-style report shown in the assignment brief."""
    mark = {"check": "\u2705", "x": "\u274c"}

    def line(dim_key, label):
        d = analysis[dim_key]
        symbol = mark.get(d["status"], "\u2753")
        return f"{symbol} {label}: {d['explanation']}\n   Citation: {d['citation']}"

    swap = analysis["project_swap"]
    if swap.get("recommended"):
        swap_text = (
            f"\u2192 Swap recommended: replace \"{swap['weak_resume_project']}\" with "
            f"\"{swap['better_portfolio_project']}\".\n   Reasoning: {swap['reasoning']}"
        )
    else:
        swap_text = f"\u2192 Current projects are already optimal. {swap.get('reasoning', '')}"

    buckets = analysis["skill_buckets"]
    score = analysis["score_breakdown"]

    return f"""FIT ANALYSIS: {analysis['title']} @ {analysis['company']}  [{analysis['job_id']}]
Deterministic score: {score['score']}  (skill_match={score['skill_match']}, experience_alignment={score['experience_alignment']}, domain_alignment={score['domain_alignment']})

{line('relevant_experience', 'Relevant Experience')}
{line('seniority', 'Seniority')}
{line('education', 'Education')}
{line('core_skills', 'Core Skills')}
{line('projects', 'Projects')}

Missing skills -- evidenced elsewhere (tailoring may add): {', '.join(buckets['evidenced_elsewhere']) or '(none)'}
Missing skills -- genuine gap (never add): {', '.join(buckets['genuine_gap']) or '(none)'}

{swap_text}

Overall: {analysis['overall_summary']}
"""


if __name__ == "__main__":
    import os

    from filtering import filter_jobs, load_jobs, load_preferences
    from scoring import top_n

    base = os.path.join(os.path.dirname(__file__), "..", "..")
    all_jobs = load_jobs(os.path.join(base, "data", "jobs.csv"))
    preferences = load_preferences(os.path.join(base, "data", "persona_preferences.json"))
    kept, _rejected = filter_jobs(all_jobs, preferences)

    profile = load_full_profile()
    top3 = top_n(kept, profile, n=3)

    outputs_dir = os.path.join(base, "outputs")
    os.makedirs(outputs_dir, exist_ok=True)

    for score_breakdown in top3:
        job = next(j for j in kept if j["job_id"] == score_breakdown["job_id"])
        print(f"Analyzing [{job['job_id']}] {job['title']} @ {job['company']} ...")
        analysis = analyze_fit(job, profile, score_breakdown)
        print(format_report(analysis))
        print("=" * 90)

        job_dir = os.path.join(outputs_dir, job["job_id"])
        os.makedirs(job_dir, exist_ok=True)
        with open(os.path.join(job_dir, "fit_analysis.json"), "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2)
        with open(os.path.join(job_dir, "fit_analysis.txt"), "w", encoding="utf-8") as f:
            f.write(format_report(analysis))
