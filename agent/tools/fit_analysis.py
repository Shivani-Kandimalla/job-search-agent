"""
Fit Analysis Tool (Section 3.3 of the assignment).

Unlike scoring.py (Section 3.2 explicitly says "deterministic; NOT an LLM
call -- a model must never generate the number"), Fit Analysis is NOT
called out as deterministic anywhere in the assignment. It's framed purely
as an LLM narrative task: "It answers: 'Tell me why this job is a good fit
for me.' Text output is enough." So the assignment's "The LLM drives --
hard-coded scripts that execute fixed steps without LLM decision-making
will lose points" rule applies here in full: all 5 dimensions' verdicts
and text must come from the model's own response, not from Python
pre-deciding them.

What Python DOES do here (and this is legitimate "tool integration," not
hard-coding a decision): compute accurate REFERENCE FACTS -- which
required skills are evidenced where, the years-of-experience comparison,
the degree-field comparison -- and hand them to the model as grounding
context in the prompt. The model still has to read those facts and write
its own check/x verdict and reasoning; Python never overwrites what the
model decided. The one place Python *does* reject part of the model's
output is the project-swap's project *names*, and even then only to
enforce the assignment's own Evidence Rule ("swapped-in projects must
exist in the portfolio file; inventing projects... is prohibited") --
it's a factual existence check, not a judgment call, and if the name is
unverifiable the tool first asks the model to self-correct before ever
falling back to "no swap."

Produces (per Section 3.3's example format):
  - Relevant Experience, Seniority, Education, Projects: single check/x
    dimension each, with citation + explanation, ALL written by the model.
  - Core Skills: aligned / missing-but-evidenced / genuine-gap lists (the
    assignment's own example format), again the model's own text -- though
    grounded by the deterministic skill_buckets given to it, so it isn't
    guessing which skills are real.
  - Projects: which on-resume project is weak (if any) + swap suggestion,
    or an explicit "already optimal" statement.
"""

import json
import re

from llm_client import chat
from profile import load_full_profile, split_skills
from scoring import _skill_present, score_job


def classify_required_skills(job: dict, profile: dict) -> dict:
    """Computes which of a job's required_skills are evidenced where in
    the candidate's real materials. This is a factual lookup (does the
    string appear in the resume vs. elsewhere in the profile?), not a
    judgment call -- similar in spirit to the job posting text itself: raw
    data the model reasons over, not a decision made on the model's
    behalf. Handed to the model as REFERENCE FACTS so it can write an
    accurate Core Skills section without having to re-derive this from
    scratch (and risk missing something or hallucinating a match).

      on_resume          -> already literally on the resume
      evidenced_elsewhere -> not on the resume, but real (portfolio-only
                              project, master skills list, or a
                              memory-learned fact)
      genuine_gap        -> not evidenced anywhere in the candidate's
                             actual materials
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


def _seniority_facts(job: dict, profile: dict, score_breakdown: dict) -> str:
    """Plain factual sentence, no verdict -- the model still has to decide
    check/x itself."""
    return (
        f"Candidate has {profile['candidate_years']} years of experience "
        f"(persona_preferences.json); posting lists "
        f"'{job['years_experience']}' (parsed minimum: "
        f"{score_breakdown['min_years_required']}+ years)."
    )


def _education_facts(job: dict, profile: dict) -> str:
    degree_fields = profile["degree_fields"]
    degree_summary = ", ".join(degree_fields) if degree_fields else "no degree listed on resume"
    text = (job.get("description", "") + " " + job.get("title", "")).lower()
    mentions_requirement = any(
        kw in text for kw in ("degree", "bachelor", "master", "b.s.", "m.s.", "phd", "ph.d")
    )
    if not mentions_requirement:
        return f"Candidate holds: {degree_summary}. Posting does not state a specific degree requirement."
    requirement_match = re.search(r"[^.]*degree[^.]*\.", text)
    requirement_text = requirement_match.group().strip() if requirement_match else "a degree requirement is mentioned but not quotable"
    return f"Candidate holds: {degree_summary}. Posting's stated requirement: \"{requirement_text}\""


def _validate_project_swap(swap: dict, on_resume_names: list, portfolio_only_names: list) -> dict:
    """Evidence Rule check: a swap is only accepted if BOTH project names
    exactly match a real project in the portfolio file. This is a factual
    existence check (does this project exist?), not a re-judgment of
    whether the swap is a good idea -- the model's own reasoning for
    *which* project to suggest is left untouched whenever it names real
    projects. Only used as a last-resort fallback after analyze_fit()
    has already given the model one chance to self-correct."""
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
        return {
            "recommended": False,
            "weak_resume_project": None,
            "better_portfolio_project": None,
            "reasoning": swap.get("reasoning") or "Current on-resume projects are retained as already optimal.",
        }

    # Named at least one project, but it doesn't exist in the real
    # portfolio -- per the assignment's own Evidence Rule ("no evidence
    # means no edit"), decline the swap rather than act on an
    # unverifiable claim. (analyze_fit() tries a self-correction turn
    # with the model before this fallback is ever reached.)
    return {
        "recommended": False,
        "weak_resume_project": None,
        "better_portfolio_project": None,
        "reasoning": "Current on-resume projects are retained as already optimal "
                     "(no verifiable, real project name was confirmed for a swap, "
                     "even after being asked to correct it -- Evidence Rule).",
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


SYSTEM_PROMPT = """You are the reasoning core of a job search agent. For ONE job posting and \
ONE candidate's real profile (resume + full project portfolio + master \
skills list + memory facts), answer: "Tell me why this job is a good fit \
for me." You must produce all five fit dimensions yourself -- Relevant \
Experience, Seniority, Education, Core Skills, Projects -- each grounded \
in something real. Nothing is pre-decided for you; you are given factual \
REFERENCE DATA (skill overlap, years comparison, degree comparison) to \
ground your answer in real facts and avoid hallucinating, but the \
check/x verdict, the citation, and the reasoning are yours to determine.

Hard rules, no exceptions:
1. Every claim must be traceable to something literally present in the \
CANDIDATE PROFILE or JOB POSTING given below. Never invent a skill, \
project, job title, achievement, or requirement.
2. Use the REFERENCE DATA (skill buckets, years comparison, degree \
comparison) as your factual source of truth for those specific facts -- \
don't contradict what it says happened (e.g. don't claim a skill is a \
genuine gap if REFERENCE DATA lists it as evidenced elsewhere) -- but YOU \
decide the check/x verdict and write the reasoning based on those facts.
3. Core Skills must be split into exactly the three groups given in \
REFERENCE DATA: aligned (already on resume), missing-but-evidenced \
(usable by resume tailoring later), genuine gaps (never to be added to \
the resume). Don't move skills between groups.
4. For Projects: actively compare each ON RESUME project's domain/tech \
against this job's domain and its "missing_evidenced" skills. If ANY \
"PORTFOLIO ONLY" project's domain or tech stack overlaps with this job \
better than an ON RESUME project does, you MUST recommend that swap -- \
don't default to "already optimal" just because the on-resume projects \
are decent; the question is whether a portfolio-only project is a BETTER \
fit, not whether the current one is acceptable. Only say "already \
optimal" if you genuinely checked every portfolio-only project and none \
of them fit this job's domain/skills better than what's already on the \
resume. You may only recommend swapping in a project from the "PORTFOLIO \
ONLY" list below (never invent one).
5. "relevant_experience" is about the NATURE and DOMAIN of the \
candidate's past work (what they built, which industry, which \
responsibilities) -- NOT about years of experience (that's Seniority's \
job). Having MORE years than required is never a reason to mark \
relevant_experience "x"; only mark it "x" if the type of work described \
doesn't relate to what this posting needs.
6. Status semantics -- mark "check" only when the candidate meets or \
exceeds the job's bar for that dimension; mark "x" only when they clearly \
fall short.
7. Citation and explanation fields must NEVER be left empty.
8. Output ONLY a single valid JSON object. No markdown code fences, no \
commentary before or after, no trailing commas.

Respond with EXACTLY this JSON shape (fill in every field):
{
  "relevant_experience": {"status": "check" or "x", "citation": "<verbatim or near-verbatim resume/portfolio detail>", "explanation": "<1-2 sentences>"},
  "seniority": {"status": "check" or "x", "citation": "<detail>", "explanation": "<1-2 sentences>"},
  "education": {"status": "check" or "x", "citation": "<detail>", "explanation": "<1-2 sentences>"},
  "core_skills": {
    "aligned": ["<skill>", "..."],
    "missing_evidenced": [{"skill": "<skill>", "evidence": "<where it's evidenced -- portfolio project name, master skills list, or memory>"}],
    "genuine_gap": ["<skill>", "..."]
  },
  "projects": {
    "current_weak_project": "<exact name from ON RESUME list, or null if already optimal>",
    "weak_project_note": "<why it contributes little to this job, or null>",
    "swap_suggestion": {"project": "<exact name from PORTFOLIO ONLY list>", "reasoning": "<1-3 sentences citing tech/domain overlap with the job>"} ,
    "already_optimal": true or false
  },
  "overall_summary": "<2-3 sentence honest overall fit summary>"
}
If already_optimal is true, set current_weak_project, weak_project_note, and swap_suggestion to null."""


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

REFERENCE DATA (factual only -- you still decide the verdict and write the reasoning):
- Required skills already on resume (use for core_skills.aligned): {', '.join(skill_buckets['on_resume']) or '(none)'}
- Required skills evidenced elsewhere in profile, not yet on resume (use for core_skills.missing_evidenced): {', '.join(skill_buckets['evidenced_elsewhere']) or '(none)'}
- Required skills not evidenced anywhere (use for core_skills.genuine_gap): {', '.join(skill_buckets['genuine_gap']) or '(none)'}
- Seniority facts: {_seniority_facts(job, profile, score_breakdown)}
- Education facts: {_education_facts(job, profile)}
- Deterministic score for context only (not a verdict on any dimension): {score_breakdown['score']} (skill_match={score_breakdown['skill_match']}, experience_alignment={score_breakdown['experience_alignment']}, domain_alignment={score_breakdown['domain_alignment']})

Now produce the JSON fit analysis described in your instructions."""


CORRECTION_PROMPT_TEMPLATE = """Your "projects" field named a project that doesn't exist in the candidate's real portfolio: \
weak_resume_project={weak!r}, swap_suggestion.project={better!r}.

The ONLY valid project names are:
- ON RESUME (valid for current_weak_project): {on_resume_names}
- PORTFOLIO ONLY (valid for swap_suggestion.project): {portfolio_only_names}

Re-send the FULL JSON object again, unchanged except: fix the "projects" \
field to use exact names from those two lists, or set already_optimal \
true with current_weak_project/swap_suggestion as null if no real project \
pairing makes sense. Output ONLY the corrected JSON object."""


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


def _is_blank(entry: dict) -> bool:
    """A dimension counts as blank if its citation is missing -- that's
    the field the assignment says must never be empty, so it's worth a
    retry even if the explanation text alone came through fine."""
    entry = entry or {}
    return not (entry.get("citation") or "").strip()


def _fill_blank_fallbacks(parsed: dict) -> dict:
    for dim in ("relevant_experience", "seniority", "education"):
        entry = parsed.get(dim) or {}
        if not entry.get("citation"):
            entry["citation"] = "(model did not provide a citation for this dimension)"
        if not entry.get("explanation"):
            entry["explanation"] = "(model did not provide an explanation for this dimension)"
        if entry.get("status") not in ("check", "x"):
            entry["status"] = "x"
        parsed[dim] = entry
    return parsed


def _swap_names(projects_field: dict) -> tuple:
    projects_field = projects_field or {}
    weak = projects_field.get("current_weak_project")
    swap = projects_field.get("swap_suggestion") or {}
    better = swap.get("project") if isinstance(swap, dict) else None
    return weak, better


def analyze_fit(job: dict, profile: dict, score_breakdown: dict = None, retries: int = 2) -> dict:
    """Returns the structured fit-analysis dict for one job. Every
    dimension's verdict/citation/explanation is the model's own output;
    Python only supplies grounding facts beforehand and fact-checks the
    project-swap's project names afterward (with a self-correction turn
    given to the model before any fallback)."""
    skill_buckets = classify_required_skills(job, profile)
    score_breakdown = score_breakdown or score_job(job, profile)
    user_prompt = _build_user_prompt(job, profile, skill_buckets, score_breakdown)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    last_error = None
    parsed = None
    raw = None
    for attempt in range(retries + 1):
        raw = chat(
            messages=messages,
            # Slightly higher temperature on retries so a re-ask isn't
            # just a coin-flip repeat of the same blank/low-quality response.
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
        any_dim_blank = any(
            _is_blank(candidate.get(dim)) for dim in ("relevant_experience", "seniority", "education")
        )
        if not any_dim_blank or is_last_attempt:
            break
        # At least one scalar dimension came back empty -- worth one more
        # try before falling back to placeholder text.

    if parsed is None:
        raise RuntimeError(
            f"Model failed to return valid JSON after {retries + 1} attempts. "
            f"Last error: {last_error}"
        )

    parsed = _fill_blank_fallbacks(parsed)

    on_resume_names = [p["name"] for p in profile["portfolio_projects"] if p["on_resume"]]
    portfolio_only_names = [p["name"] for p in profile["portfolio_projects"] if not p["on_resume"]]

    weak, better = _swap_names(parsed.get("projects"))
    weak_valid = not weak or weak.lower() in [n.lower() for n in on_resume_names]
    better_valid = not better or better.lower() in [n.lower() for n in portfolio_only_names]

    if (weak or better) and not (weak_valid and better_valid):
        # Give the model one self-correction turn (a real second LLM call,
        # visible in the trace) instead of silently overwriting its answer.
        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": CORRECTION_PROMPT_TEMPLATE.format(
                weak=weak, better=better,
                on_resume_names=on_resume_names,
                portfolio_only_names=portfolio_only_names,
            ),
        })
        try:
            corrected_raw = chat(messages=messages, temperature=0.2, response_format={"type": "json_object"})
            corrected = _extract_json(corrected_raw)
            corrected = _fill_blank_fallbacks(corrected)
            parsed["projects"] = corrected.get("projects") or parsed.get("projects")
        except (ValueError, json.JSONDecodeError):
            pass  # fall through to the fact-check fallback below

    projects_field = parsed.get("projects") or {}
    parsed["projects"] = projects_field
    weak, better = _swap_names(projects_field)
    swap_reasoning = ((projects_field.get("swap_suggestion") or {}).get("reasoning")
                       if isinstance(projects_field.get("swap_suggestion"), dict) else None)
    verified_swap = _validate_project_swap(
        {
            "weak_resume_project": weak,
            "better_portfolio_project": better,
            "reasoning": swap_reasoning,
        },
        on_resume_names,
        portfolio_only_names,
    )
    parsed["project_swap"] = verified_swap
    parsed["projects"]["already_optimal"] = not verified_swap["recommended"]
    if not verified_swap["recommended"]:
        parsed["projects"]["current_weak_project"] = None
        parsed["projects"]["swap_suggestion"] = None

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

    core = analysis["core_skills"] or {}
    aligned = core.get("aligned") or []
    missing_evidenced = core.get("missing_evidenced") or []
    genuine_gap = core.get("genuine_gap") or []
    missing_evidenced_str = ", ".join(
        f"{m['skill']} ({m.get('evidence', 'evidenced elsewhere')})" if isinstance(m, dict) else str(m)
        for m in missing_evidenced
    ) or "(none)"

    swap = analysis["project_swap"]
    if swap.get("recommended"):
        swap_text = (
            f"\u2705 Swap Suggestion: Replace \"{swap['weak_resume_project']}\" with "
            f"\"{swap['better_portfolio_project']}\".\n   Reasoning: {swap['reasoning']}"
        )
    else:
        swap_text = f"\u2705 Current projects are already optimal. {swap.get('reasoning', '')}"

    score = analysis["score_breakdown"]

    return f"""FIT ANALYSIS: {analysis['title']} @ {analysis['company']}  [{analysis['job_id']}]
Deterministic score (from scoring.py, not this tool): {score['score']}  (skill_match={score['skill_match']}, experience_alignment={score['experience_alignment']}, domain_alignment={score['domain_alignment']})

{line('relevant_experience', 'Relevant Experience')}
{line('seniority', 'Seniority')}
{line('education', 'Education')}

Core Skills:
\u2705 Aligned: {', '.join(aligned) or '(none)'}
\u274c Missing but evidenced in profile: {missing_evidenced_str}
\u274c Genuine gaps: {', '.join(genuine_gap) or '(none)'}

Projects:
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
