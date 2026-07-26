"""
Cover Letter Tool (Section 3.6 of the assignment) -- the mandatory final
step, run once per approved Top-3 job.

Tooling decision (owned by this workstream): the letter is written as
LaTeX and compiled with the SAME `pdflatex` toolchain the resume already
needs, rather than pulling in a separate Python PDF library. Reasons:
  - zero new dependencies (pdflatex is already a hard requirement of
    agent/tools/tailoring.py, so nothing new to install for a grader),
  - the letter visually matches the resume (same fonts/margins),
  - the one-page check is the same `pypdf` page count used for the resume,
    so "one-page PDF each" is verified the same way in both tools.
The compile/page-count/escaping helpers are imported from tailoring.py on
purpose -- one implementation, used by both PDF-producing tools.

Structure produced (all six elements the assignment lists):
  contact header -> date -> company block -> greeting -> opening naming the
  role + company with a hook drawn from that job's Company Details field ->
  1-2 body paragraphs mapping REAL resume/portfolio experience to the job
  description -> a skills line -> closing.

No-fabrication rules, enforced in code (not trusted to the model):
  - the skills line is NOT written by the LLM: it is built from the
    deterministic skill_buckets (on_resume + evidenced_elsewhere, which
    includes memory-learned skills), each with a citation;
  - a genuine-gap skill appearing anywhere in the generated prose is
    rejected (one self-correction turn, then a deterministic fallback
    letter built only from real profile text);
  - every number in the prose must be traceable to the real resume or
    portfolio text (same `_no_new_numbers` check tailoring.py uses);
  - the role title, company name, and contact details are inserted by the
    template from data/jobs.csv and resume.tex -- the model never gets to
    restate them wrongly.
"""

import json
import os
import re
import shutil
from datetime import datetime

from fit_analysis import _extract_json
from filtering import load_jobs
from llm_client import chat
from memory_store import citation_for, load_memory
from profile import load_full_profile
# Single implementation of the LaTeX plumbing, shared with the resume tool.
from tailoring import (
    _compile,
    _extract_summary,
    _latex_escape,
    _no_new_numbers,
    _page_count,
    _shorten,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RESUME_TEX_PATH = os.path.join(REPO_ROOT, "resume", "resume.tex")

MAX_TRIM_ATTEMPTS = 4


# ---------------------------------------------------------------------------
# Contact header -- parsed from the real resume, never invented
# ---------------------------------------------------------------------------

def contact_header(resume_tex: str = None) -> dict:
    """Reads the candidate's contact block straight out of resume.tex so the
    letter head and the resume head can never drift apart."""
    if resume_tex is None:
        with open(RESUME_TEX_PATH, encoding="utf-8") as f:
            resume_tex = f.read()

    name = re.search(r"\{\\Huge\s+\\scshape\s+([^}]+)\}", resume_tex)
    email = re.search(r"mailto:([^}]+)\}", resume_tex)
    github = re.search(r"\\href\{(https://github\.com/[^}]+)\}", resume_tex)
    contact_line = re.search(r"\\vspace\{2pt\}\s*\n\s*([^\n]+)", resume_tex)

    location, phone = "", ""
    if contact_line:
        parts = [p.strip() for p in contact_line.group(1).split("$|$")]
        if parts:
            location = parts[0]
        if len(parts) > 1:
            phone = parts[1]

    return {
        "name": name.group(1).strip() if name else "",
        "location": location,
        "phone": phone,
        "email": email.group(1).strip() if email else "",
        "github": github.group(1).strip() if github else "",
    }


# ---------------------------------------------------------------------------
# Deterministic skills line (Evidence Rule -- no LLM judgment involved)
# ---------------------------------------------------------------------------

def skills_line_items(fit_analysis: dict, profile: dict) -> list:
    """The letter's skills line, built exactly like tailoring.py builds the
    resume's skills additions: from the job's required skills that are
    genuinely evidenced (on the resume, or elsewhere in the profile /
    master skills list / memory). Genuine gaps are never listed.

    Returns [{"skill": ..., "citation": ...}] so the change/evidence log
    can show where each claimed skill comes from.
    """
    buckets = fit_analysis.get("skill_buckets", {})
    memory = profile.get("memory") or load_memory()
    memory_skills_lower = [s.lower() for s in profile.get("memory_skills", [])]

    items, seen = [], set()
    for skill in buckets.get("on_resume", []):
        key = skill.strip().lower()
        if key and key not in seen:
            seen.add(key)
            items.append({"skill": skill, "citation": "resume.tex (skill_buckets.on_resume)"})

    for skill in buckets.get("evidenced_elsewhere", []):
        key = skill.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        if any(m in key or key in m for m in memory_skills_lower):
            citation = citation_for(skill, memory)
        else:
            citation = "portfolio.txt / master skills list (skill_buckets.evidenced_elsewhere)"
        items.append({"skill": skill, "citation": citation})

    return items


def _genuine_gaps(fit_analysis: dict) -> list:
    return list((fit_analysis.get("skill_buckets") or {}).get("genuine_gap") or [])


def _gap_mentions(text: str, gaps: list) -> list:
    """Which genuine-gap skills did the model slip into the prose? Matched
    on whole words so 'JAX' doesn't fire on 'jaxton' and a multi-word gap
    like 'query understanding' is matched as a phrase."""
    lowered = (text or "").lower()
    hits = []
    for gap in gaps:
        gap_clean = re.sub(r"\s*\([^)]*\)", "", gap).strip().lower()
        if not gap_clean:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(gap_clean)}(?![a-z0-9])", lowered):
            hits.append(gap)
    return hits


# ---------------------------------------------------------------------------
# LLM call: opening + body paragraphs + closing (the only creative step)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the cover-letter step of a job search agent. You are given ONE \
job posting (including a short "Company Details" blurb), the candidate's \
REAL resume text, their REAL project portfolio, and the already-computed \
fit analysis for this job. Write the prose of a short, one-page cover \
letter.

You write ONLY these parts: the opening paragraph, one or two body \
paragraphs, and a closing paragraph. The contact header, date, greeting, \
and the skills line are added by the program around your text -- do not \
write them yourself.

Hard rules, no exceptions:
1. The opening paragraph must name the exact job title and the exact \
company name given below, and must include a specific hook drawn from the \
"Company Details" blurb (something about what that company actually does) \
-- not a generic "I am excited to apply" sentence.
2. Body paragraphs must map the candidate's REAL experience (employers, \
projects, and achievements that literally appear in the resume or \
portfolio text below) to what this job description asks for. Name real \
employers/projects; never invent one.
3. Never claim, imply, or mention any skill listed under GENUINE GAPS \
below -- those are skills the candidate does not have. Those exact words \
must not appear anywhere in your letter: not as a claim, not as something \
being learned, and not even when describing what the company or the role \
does. If a gap skill is central to the posting, write about the \
neighbouring work the candidate HAS done instead of naming the gap.
4. Only use numbers (percentages, metrics, years) that literally appear in \
the resume or portfolio text below. Never invent or round a metric.
5. Keep it tight: opening 2-3 sentences, each body paragraph 3-5 \
sentences, closing 2-3 sentences. It must fit on one page with the header \
and skills line.
6. Plain prose only -- no bullet points, no markdown, no LaTeX commands, \
no placeholders like [Company].
7. Output ONLY a single valid JSON object. No markdown code fences, no \
commentary before or after, no trailing commas.

Respond with EXACTLY this JSON shape:
{
  "opening": "<string>",
  "body_paragraphs": ["<string>", "<string (optional -- 1 or 2 items total)>"],
  "closing": "<string>",
  "reasoning": "<1-2 sentences: which company hook you used and which real experience you mapped to which requirement>"
}"""


def _build_user_prompt(job: dict, fit_analysis: dict, profile: dict, skills: list) -> str:
    core = fit_analysis.get("core_skills") or {}
    gaps = _genuine_gaps(fit_analysis)
    swap = fit_analysis.get("project_swap") or {}
    swap_note = ""
    if swap.get("recommended"):
        swap_note = (
            f"\nNote: for this job the resume now features the portfolio project "
            f"\"{swap['better_portfolio_project']}\" (it replaced "
            f"\"{swap['weak_resume_project']}\"), so that project is a good one to "
            f"reference in the body."
        )

    return f"""JOB POSTING
Title: {job['title']}
Company: {job['company']}
Industry/Domain: {job['industry_domain']}
Location: {job['location']}
Required skills: {job['required_skills']}
Years of experience required: {job['years_experience']}
Description:
{job['description']}

COMPANY DETAILS (use this for the opening hook):
{job['company_details']}

CANDIDATE RESUME (plain text -- the only employers, titles, dates and metrics you may use):
{profile['resume_plaintext']}

CANDIDATE PROJECT PORTFOLIO (real projects, including ones not on the resume):
{profile['portfolio_text']}

FIT ANALYSIS (already computed -- do not re-decide any verdict)
Overall: {fit_analysis.get('overall_summary', '')}
Relevant experience: {(fit_analysis.get('relevant_experience') or {}).get('explanation', '')}
Aligned skills you may claim: {', '.join(core.get('aligned') or []) or '(none)'}
Skills evidenced elsewhere in the profile you may also claim: {', '.join(s['skill'] for s in skills) or '(none)'}
FORBIDDEN PHRASES (genuine gaps -- these exact words must not appear anywhere in your letter, in any context, including when describing the company or the role): {', '.join(gaps) or '(none)'}{swap_note}

The program will add this skills line under your body paragraphs, so don't repeat it verbatim:
"{', '.join(s['skill'] for s in skills)}"

Now produce the JSON object described in your instructions."""


CORRECTION_PROMPT_TEMPLATE = """Your draft broke a hard rule:
{issues}

Re-send the FULL JSON object again, unchanged except: fix the flagged \
problem(s). Output ONLY the corrected JSON object."""


def _sanitize(draft: dict) -> dict:
    """Shape-fixes that don't need a whole correction turn: local models
    sometimes echo a field name back as a paragraph ("closing") or run past
    the requested two body paragraphs. Drop the junk, keep at most two
    paragraphs, and let _validate() catch anything substantive that's left."""
    paragraphs = [
        " ".join(str(p).split())
        for p in (draft.get("body_paragraphs") or [])
        if isinstance(p, str) and len(str(p).strip()) > 60
    ]
    draft["body_paragraphs"] = paragraphs[:2]
    draft["opening"] = " ".join(str(draft.get("opening") or "").split())
    draft["closing"] = " ".join(str(draft.get("closing") or "").split())
    return draft


def _validate(draft: dict, job: dict, fit_analysis: dict, profile: dict) -> list:
    """Code-level no-fabrication checks. Returns a list of human-readable
    issues (empty list == the draft is clean)."""
    prose = " ".join(
        [draft.get("opening") or "", *(draft.get("body_paragraphs") or []), draft.get("closing") or ""]
    )
    issues = []

    if not prose.strip():
        issues.append("the letter body came back empty")
        return issues

    if not draft.get("body_paragraphs"):
        issues.append("body_paragraphs: needs one or two real paragraphs of 3-5 sentences each")
    if len((draft.get("closing") or "").strip()) < 40:
        issues.append("closing: needs a real 2-3 sentence closing paragraph, not a placeholder or an empty string")

    if job["company"].lower() not in (draft.get("opening") or "").lower():
        issues.append(f"opening: must name the company exactly as \"{job['company']}\"")

    title_tokens = [t for t in re.findall(r"[a-z]+", job["title"].lower()) if len(t) > 3]
    opening_lower = (draft.get("opening") or "").lower()
    if title_tokens and sum(1 for t in title_tokens if t in opening_lower) / len(title_tokens) < 0.5:
        issues.append(f"opening: must name the role as \"{job['title']}\"")

    gap_hits = _gap_mentions(prose, _genuine_gaps(fit_analysis))
    if gap_hits:
        issues.append(
            "the letter uses the forbidden phrase(s) "
            + ", ".join(f'"{g}"' for g in gap_hits)
            + " -- these are skills the candidate does not have. Delete those exact words "
              "everywhere they appear (including in descriptions of the company or the role) "
              "and rewrite those sentences around work the candidate has actually done"
        )

    source_text = profile["resume_plaintext"] + " " + profile["portfolio_text"]
    if not _no_new_numbers(source_text, prose):
        issues.append("the letter states a number that appears nowhere in the real resume or portfolio")

    return issues


def _fallback_draft(job: dict, fit_analysis: dict, profile: dict, skills: list) -> dict:
    """Deterministic, guaranteed-grounded letter used only if the model
    can't produce a clean draft in two turns.

    Everything here is copied from text that already exists: the job's own
    Company Details blurb, the resume's own Professional Summary, and the
    project the tailored resume actually features. Nothing is generated, so
    it cannot fabricate -- and because it only quotes the candidate's own
    material, it cannot name a genuine-gap skill either.
    """
    summary = _extract_summary(profile["resume_text"]).strip()

    swap = fit_analysis.get("project_swap") or {}
    featured = None
    if swap.get("recommended"):
        featured = next((p for p in profile["portfolio_projects"]
                         if p["name"].lower() == (swap.get("better_portfolio_project") or "").lower()), None)
    if featured is None:
        featured = next((p for p in profile["portfolio_projects"] if p["on_resume"]), None)

    project_sentence = ""
    if featured:
        project_sentence = (
            f" My \"{featured['name']}\" project ({', '.join(featured['tech_stack'])}; "
            f"{featured['domain']}) is the closest match to this role's day-to-day work."
        )

    skills_sentence = ""
    if skills:
        skills_sentence = (
            " The requirements I can evidence directly from my resume and portfolio are "
            + ", ".join(s["skill"] for s in skills) + "."
        )

    return {
        "opening": (
            f"I am writing to apply for the {job['title']} position at {job['company']}. "
            f"{job['company_details'].strip()} That is the kind of problem I want to work on next."
        ),
        "body_paragraphs": [summary + project_sentence + skills_sentence],
        "closing": (
            f"I would welcome the chance to discuss how my background fits the {job['title']} role at "
            f"{job['company']}. Thank you for your time and consideration."
        ),
        "reasoning": "Deterministic fallback letter -- the model's two drafts did not pass the "
                     "no-fabrication checks, so the letter was assembled verbatim from the job "
                     "posting's Company Details, the resume's own Professional Summary, and the "
                     "featured portfolio project.",
    }


def _draft_letter(job: dict, fit_analysis: dict, profile: dict, skills: list) -> tuple:
    """Returns (draft, validation_log). One self-correction turn (a real
    second LLM call, same pattern fit_analysis.py and tailoring.py use)
    before the deterministic fallback is ever reached."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(job, fit_analysis, profile, skills)},
    ]
    validation_log = []

    try:
        raw = chat(messages=messages, temperature=0.3, response_format={"type": "json_object"})
        draft = _sanitize(_extract_json(raw))
    except (ValueError, json.JSONDecodeError) as e:
        validation_log.append(f"first draft was not valid JSON ({e}) -- using deterministic fallback")
        return _fallback_draft(job, fit_analysis, profile, skills), validation_log

    issues = _validate(draft, job, fit_analysis, profile)
    if not issues:
        validation_log.append("first draft passed all no-fabrication checks")
        return draft, validation_log

    validation_log.append("first draft failed: " + "; ".join(issues))
    messages.append({"role": "assistant", "content": raw})
    messages.append({"role": "user", "content": CORRECTION_PROMPT_TEMPLATE.format(
        issues="\n".join(f"- {i}" for i in issues))})

    try:
        corrected_raw = chat(messages=messages, temperature=0.2, response_format={"type": "json_object"})
        corrected = _sanitize(_extract_json(corrected_raw))
    except (ValueError, json.JSONDecodeError) as e:
        validation_log.append(f"correction turn was not valid JSON ({e}) -- using deterministic fallback")
        return _fallback_draft(job, fit_analysis, profile, skills), validation_log

    issues = _validate(corrected, job, fit_analysis, profile)
    if issues:
        validation_log.append("correction turn still failed: " + "; ".join(issues)
                              + " -- using deterministic fallback")
        return _fallback_draft(job, fit_analysis, profile, skills), validation_log

    validation_log.append("correction turn passed all no-fabrication checks")
    return corrected, validation_log


# ---------------------------------------------------------------------------
# LaTeX rendering + One-Page Rule
# ---------------------------------------------------------------------------

# Placeholders are <<TOKENS>> rather than %-style or {}-style format specs:
# a LaTeX source is full of literal % (comments) and { } (every command), so
# both of Python's usual templating syntaxes would need escaping everywhere.
LETTER_TEMPLATE = r"""%-------------------------------------------------------------------------------
% Cover letter generated by the Job Search Agent's Cover Letter Tool.
% Fictional persona -- see data/persona_preferences.json.
%-------------------------------------------------------------------------------
\documentclass[letterpaper,11pt]{article}

\usepackage[margin=1in]{geometry}
\usepackage[hidelinks]{hyperref}

\pagestyle{empty}
\raggedright
\setlength{\parindent}{0pt}
\setlength{\parskip}{8pt}

\begin{document}

\begin{center}
    {\Large \scshape <<NAME>>} \\ \vspace{2pt}
    \small <<CONTACT>>
\end{center}
\vspace{6pt}
\hrule
\vspace{10pt}

<<DATE>>

\textbf{<<COMPANY>>} \\
Re: <<TITLE>>

\vspace{4pt}

Dear <<COMPANY>> Hiring Team,

<<OPENING>>

<<BODY>>

\textbf{Relevant skills:} <<SKILLS>>

<<CLOSING>>

\vspace{10pt}
Sincerely, \\
<<NAME>>

\end{document}
"""


def _render_tex(job: dict, header: dict, draft: dict, skills: list) -> str:
    contact_bits = [header.get("location"), header.get("phone"), header.get("email")]
    contact = r" $|$ ".join(_latex_escape(b) for b in contact_bits if b)
    if header.get("github"):
        contact += r" $|$ " + _latex_escape(header["github"].replace("https://", ""))

    body = "\n\n".join(
        _latex_escape(" ".join(p.split())) for p in (draft.get("body_paragraphs") or []) if p and p.strip()
    )

    fields = {
        "NAME": _latex_escape(header.get("name", "")),
        "CONTACT": contact,
        "DATE": _latex_escape(datetime.now().strftime("%B %d, %Y")),
        "COMPANY": _latex_escape(job["company"]),
        "TITLE": _latex_escape(job["title"]),
        "OPENING": _latex_escape(" ".join((draft.get("opening") or "").split())),
        "BODY": body,
        "SKILLS": _latex_escape(", ".join(s["skill"] for s in skills)),
        "CLOSING": _latex_escape(" ".join((draft.get("closing") or "").split())),
    }
    tex = LETTER_TEMPLATE
    for token, value in fields.items():
        tex = tex.replace(f"<<{token}>>", value)
    return tex


def _enforce_one_page(job, header, draft, skills, tex_path, output_dir, log) -> tuple:
    """Same rule as the resume: verify the page count programmatically and
    trim until it's exactly one page. Trim order here (this workstream's
    call): drop the second body paragraph first, then shorten the first
    body paragraph, then the opening -- the skills line and the closing are
    the letter's required elements and are never dropped."""
    tex = _render_tex(job, header, draft, skills)
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(tex)
    pdf_path = _compile(tex_path, output_dir)
    pages = _page_count(pdf_path)

    attempts = 0
    while pages > 1 and attempts < MAX_TRIM_ATTEMPTS:
        attempts += 1
        paragraphs = draft.get("body_paragraphs") or []
        if len(paragraphs) > 1:
            draft["body_paragraphs"] = paragraphs[:-1]
            log.append("One-Page Rule: dropped the last body paragraph")
        elif paragraphs and len(paragraphs[0]) > 400:
            draft["body_paragraphs"] = [_shorten(paragraphs[0], 400)]
            log.append("One-Page Rule: shortened the body paragraph")
        elif len(draft.get("opening") or "") > 300:
            draft["opening"] = _shorten(draft["opening"], 300)
            log.append("One-Page Rule: shortened the opening paragraph")
        else:
            break

        tex = _render_tex(job, header, draft, skills)
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex)
        pdf_path = _compile(tex_path, output_dir)
        pages = _page_count(pdf_path)

    if pages != 1:
        raise RuntimeError(
            f"Cover letter for {job['job_id']} is {pages} pages after {attempts} trim attempts."
        )
    return tex, pdf_path


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_cover_letter(job: dict, fit_analysis: dict, profile: dict) -> dict:
    """Writes outputs/<job_id>/cover_letter.{tex,pdf} for ONE approved job
    and returns {"job_id", "tex_path", "pdf_path", "skills_cited",
    "evidence_log", "reasoning"}.

    Only ever called after the human review pause has APPROVED that job's
    resume (Section 3.5: "Only after approval does the agent compile the
    final PDFs and move on").
    """
    job_id = job["job_id"]
    job_dir = os.path.join(REPO_ROOT, "outputs", job_id)
    os.makedirs(job_dir, exist_ok=True)

    header = contact_header()
    skills = skills_line_items(fit_analysis, profile)
    draft, evidence_log = _draft_letter(job, fit_analysis, profile, skills)

    tex_path = os.path.join(job_dir, "cover_letter.tex")
    tex, pdf_path = _enforce_one_page(job, header, draft, skills, tex_path, job_dir, evidence_log)

    final_pdf_path = os.path.join(job_dir, "cover_letter.pdf")
    if os.path.abspath(pdf_path) != os.path.abspath(final_pdf_path):
        shutil.copyfile(pdf_path, final_pdf_path)
        os.remove(pdf_path)

    result = {
        "job_id": job_id,
        "tex_path": tex_path,
        "pdf_path": final_pdf_path,
        "skills_cited": skills,
        "evidence_log": evidence_log,
        "reasoning": draft.get("reasoning", ""),
        "letter_text": {
            "opening": draft.get("opening", ""),
            "body_paragraphs": draft.get("body_paragraphs", []),
            "skills_line": ", ".join(s["skill"] for s in skills),
            "closing": draft.get("closing", ""),
        },
    }
    with open(os.path.join(job_dir, "cover_letter_log.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == "__main__":
    outputs_dir = os.path.join(REPO_ROOT, "outputs")
    with open(os.path.join(outputs_dir, "ranked_jobs.json"), encoding="utf-8") as f:
        top3_job_ids = json.load(f)["top3_job_ids"]

    all_jobs = {j["job_id"]: j for j in load_jobs(os.path.join(REPO_ROOT, "data", "jobs.csv"))}
    profile = load_full_profile()

    for job_id in top3_job_ids:
        job = all_jobs[job_id]
        with open(os.path.join(outputs_dir, job_id, "fit_analysis.json"), encoding="utf-8") as f:
            fit_analysis = json.load(f)
        print(f"Writing cover letter for [{job_id}] {job['title']} @ {job['company']} ...")
        result = generate_cover_letter(job, fit_analysis, profile)
        for line in result["evidence_log"]:
            print(f"    {line}")
        print(f"  -> {result['pdf_path']}")
