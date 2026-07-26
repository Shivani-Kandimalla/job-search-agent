"""
Resume Tailoring Tool (Section 3.4 of the assignment).

Takes one Top-3 job's saved fit_analysis.json (already fact-checked in
Stage 2 -- project_swap and skill_buckets are deterministic, not
re-decided here) plus resume/resume.tex and data/portfolio.txt, and
produces a tailored, recompiled, one-page resume PDF with a citation-backed
change log.

Only four edits are ever made, located via the AGENT-EDIT-TARGET /
AGENT-SWAP-TARGET comments already in resume.tex:
  1. Professional Summary rewrite
  2. Exactly 2 experience bullet rewrites
  3. Skills section: surface-form alignment + evidenced additions
  4. Project swap (only if fit_analysis["project_swap"]["recommended"])

Evidence Rule enforcement is code-level, not LLM-trusted:
  - Skill additions/highlights are read straight from fit_analysis's
    already-deterministic skill_buckets (Stage 2's own Python-computed
    string match against resume/portfolio/master-skills/memory). The LLM
    never proposes which skills to add -- it only writes the summary and
    bullet prose; see _skills_to_add().
  - The project swap is Stage 2's already fact-checked project_swap field
    -- executed here, never re-decided.
  - Any number (percentage, AUC, latency, etc.) in an original bullet, or
    in the real portfolio project description for a swapped-in project,
    must be preserved exactly in the LLM's rewrite; a rewrite that
    drops/changes/invents a number gets one correction turn, then falls
    back to the original (or a plain deterministic) text unchanged. See
    _same_numbers() / _no_new_numbers().
"""

import json
import os
import re
import shutil
import subprocess

from fit_analysis import _extract_json
from filtering import load_jobs
from llm_client import chat
from memory_store import citation_for as memory_citation_for
from profile import load_full_profile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RESUME_TEX_PATH = os.path.join(REPO_ROOT, "resume", "resume.tex")
RESUME_PDF_PATH = os.path.join(REPO_ROOT, "resume", "resume.pdf")

MAX_TRIM_ATTEMPTS = 5

_LATEX_SPECIAL = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def _latex_escape(text: str) -> str:
    return "".join(_LATEX_SPECIAL.get(ch, ch) for ch in text)


_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")


def _numbers(text: str) -> set:
    return set(_NUMBER_RE.findall(text or ""))


def _same_numbers(original: str, rewritten: str) -> bool:
    """Bullet rewrites may reframe wording, but every number must survive
    unchanged and no new number may appear -- a metric is a fact, not
    something the LLM gets to edit."""
    return _numbers(original) == _numbers(rewritten)


def _no_new_numbers(source_text: str, generated_text: str) -> bool:
    """The summary / swapped-project bullet may omit numbers, but any
    number they DO state must be traceable to the real source text."""
    return _numbers(generated_text).issubset(_numbers(source_text))


# ---------------------------------------------------------------------------
# Deterministic skill selection (Evidence Rule -- no LLM judgment involved)
# ---------------------------------------------------------------------------

def _skills_to_add(fit_analysis: dict, resume_text_lower: str, profile: dict = None) -> list:
    """Two behaviors, both explicitly allowed by Section 3.4, both
    computed from fit_analysis's already-deterministic skill_buckets:
      - surface-form alignment: an "on_resume" bucket skill (i.e. Stage
        2's scoring already counted this job's required-skill wording as
        matched) that isn't literally the wording used on the resume --
        e.g. resume says "ML", job says "machine learning" -- gets added
        as the job's own phrasing so keyword matching improves without
        inventing new content.
      - evidenced additions: "evidenced_elsewhere" bucket skills -- real
        (evidenced in the portfolio, master skills list, or memory), just
        not yet listed on the resume.
    Returns an ordered, de-duplicated list of {"skill", "citation"} dicts.

    `profile` is optional and only used to sharpen the citation: a skill
    the candidate taught the agent during a review pause is cited to
    memory.json (with its provenance) rather than to the generic
    "evidenced_elsewhere" bucket, so the change log shows exactly where a
    memory-sourced edit came from (Section 3.5).
    """
    buckets = fit_analysis.get("skill_buckets", {})
    memory_skills = [s.lower() for s in (profile or {}).get("memory_skills", [])]
    additions = []
    seen = set()

    for skill in buckets.get("on_resume", []):
        if skill.strip().lower() in resume_text_lower:
            continue  # already literally on the resume, nothing to add
        key = skill.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        additions.append({
            "skill": skill,
            "citation": "skill_buckets.on_resume (surface-form alignment -- "
                        "matched via synonym/token overlap, not literal resume wording)",
        })

    for skill in buckets.get("evidenced_elsewhere", []):
        key = skill.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        if any(m in key or key in m for m in memory_skills):
            citation = memory_citation_for(skill, (profile or {}).get("memory"))
        else:
            citation = "skill_buckets.evidenced_elsewhere"
        additions.append({"skill": skill, "citation": citation})

    return additions


# ---------------------------------------------------------------------------
# resume.tex edit-point extraction / application (AGENT-EDIT-TARGET markers)
# ---------------------------------------------------------------------------

def _extract_summary(tex: str) -> str:
    match = re.search(r"% AGENT-EDIT-TARGET: summary\s*\n(.*?)\n\n%----------EDUCATION", tex, re.DOTALL)
    if not match:
        raise ValueError("Could not locate the summary AGENT-EDIT-TARGET block in resume.tex")
    return " ".join(match.group(1).split())


def _replace_summary(tex: str, new_summary: str) -> str:
    escaped = _latex_escape(" ".join(new_summary.split()))
    return re.sub(
        r"(% AGENT-EDIT-TARGET: summary\s*\n).*?(\n\n%----------EDUCATION)",
        lambda m: m.group(1) + escaped + m.group(2),
        tex,
        count=1,
        flags=re.DOTALL,
    )


def _extract_bullet(tex: str, bullet_id: str) -> str:
    pattern = rf"% AGENT-EDIT-TARGET: {bullet_id}\s*\n\s*\\resumeItem\{{([^{{}}]*)\}}"
    match = re.search(pattern, tex)
    if not match:
        raise ValueError(f"Could not locate {bullet_id} AGENT-EDIT-TARGET block in resume.tex")
    return " ".join(match.group(1).split())


def _replace_bullet(tex: str, bullet_id: str, new_text: str) -> str:
    escaped = _latex_escape(" ".join(new_text.split()))
    pattern = rf"(% AGENT-EDIT-TARGET: {bullet_id}\s*\n\s*\\resumeItem\{{)([^{{}}]*)(\}})"
    return re.sub(pattern, lambda m: m.group(1) + escaped + m.group(3), tex, count=1)


_ADDITIONAL_SKILLS_LINE_RE = re.compile(
    r"[ \t]*\\small\\item\{\\textbf\{Additional \(aligned with this role\):\}[^{}]*\}\n"
)


def _remove_additional_skills_line(tex: str) -> str:
    return _ADDITIONAL_SKILLS_LINE_RE.sub("", tex, count=1)


def _insert_additional_skills(tex: str, additions: list) -> str:
    tex = _remove_additional_skills_line(tex)
    if not additions:
        return tex
    skills_str = ", ".join(_latex_escape(a["skill"]) for a in additions)
    marker = "% AGENT-EDIT-TARGET: skills"
    marker_idx = tex.index(marker)
    end_idx = tex.index(r"\end{itemize}", marker_idx)
    insertion = f"  \\small\\item{{\\textbf{{Additional (aligned with this role):}} {skills_str}}}\n"
    return tex[:end_idx] + insertion + tex[end_idx:]


_PROJECT_BLOCK_RE = re.compile(
    r"% AGENT-SWAP-TARGET: project-(\d+)\s*\n"
    r"\s*\\resumeEntry\{([^{}]*)\}\{([^{}]*)\}\s*\n"
    r"\s*\{([^{}]*)\}\{([^{}]*)\}\s*\n"
    r"\s*\\resumeItemListStart\n"
    r"(.*?)"
    r"\\resumeItemListEnd",
    re.DOTALL,
)


def _find_project_block(tex: str, project_name: str):
    for match in _PROJECT_BLOCK_RE.finditer(tex):
        if match.group(2).strip().lower() == project_name.strip().lower():
            return match
    return None


def _replace_project(tex: str, weak_project_name: str, new_project: dict, new_bullet: str) -> str:
    match = _find_project_block(tex, weak_project_name)
    if not match:
        raise ValueError(f"Could not locate resume project block for '{weak_project_name}'")

    marker_n = match.group(1)
    year = match.group(3).strip()  # reuse the replaced project's year -- don't invent a new one
    name = _latex_escape(new_project["name"])
    tech = _latex_escape(", ".join(new_project["tech_stack"]))
    domain = _latex_escape(new_project["domain"])
    bullet = _latex_escape(" ".join(new_bullet.split()))

    replacement = (
        f"% AGENT-SWAP-TARGET: project-{marker_n}\n"
        f"  \\resumeEntry{{{name}}}{{{year}}}\n"
        f"    {{Tech Stack: {tech}}}{{{domain}}}\n"
        f"  \\resumeItemListStart\n"
        f"    \\resumeItem{{{bullet}}}\n"
        f"  \\resumeItemListEnd"
    )
    return tex[:match.start()] + replacement + tex[match.end():]


# ---------------------------------------------------------------------------
# pdflatex recompilation + One-Page Rule
# ---------------------------------------------------------------------------

def _find_pdflatex() -> str:
    env_override = os.environ.get("PDFLATEX_PATH")
    if env_override and os.path.isfile(env_override):
        return env_override
    found = shutil.which("pdflatex")
    if found:
        return found
    fallback = r"C:\Users\mguitoun\texlive\2026\bin\windows\pdflatex.exe"
    if os.path.isfile(fallback):
        return fallback
    raise RuntimeError(
        "pdflatex not found on PATH. Set the PDFLATEX_PATH env var to its full "
        "path, or add your TeX distribution's bin directory to PATH."
    )


def _compile(tex_path: str, output_dir: str) -> str:
    pdflatex = _find_pdflatex()
    result = subprocess.run(
        [pdflatex, "-interaction=nonstopmode", "-halt-on-error",
         "-output-directory", output_dir, tex_path],
        capture_output=True, text=True,
    )
    pdf_path = os.path.join(output_dir, os.path.splitext(os.path.basename(tex_path))[0] + ".pdf")
    if result.returncode != 0 or not os.path.isfile(pdf_path):
        error_lines = [l for l in result.stdout.splitlines() if l.startswith("!")]
        raise RuntimeError(
            f"pdflatex failed compiling {tex_path}:\n" + "\n".join(error_lines or [result.stdout[-2000:]])
        )
    return pdf_path


def _page_count(pdf_path: str) -> int:
    from pypdf import PdfReader
    return len(PdfReader(pdf_path).pages)


def _shorten(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars].rsplit(" ", 1)[0].rstrip(".,;: ")
    return truncated + "."


def _enforce_one_page(tex: str, tex_path: str, output_dir: str, state: dict, log: list) -> tuple:
    """Recompiles, and if the PDF is more than one page, trims content in
    a fixed priority order (my call as the Tailoring workstream owner,
    documented in handoff/tailoring_handoff.md): summary first (least
    information-dense edit), then the 2 tailored bullets, then the
    lowest-priority added skills last. Re-recompiles after each trim.
    Returns (final_tex, pdf_path)."""
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(tex)
    pdf_path = _compile(tex_path, output_dir)
    pages = _page_count(pdf_path)
    attempts = 0
    trim_stage = 0  # 0=summary, 1=bullets, 2=skills

    while pages > 1 and attempts < MAX_TRIM_ATTEMPTS:
        attempts += 1
        progressed = False

        if trim_stage == 0:
            shortened = _shorten(state["summary"], 320)
            if shortened != state["summary"]:
                state["summary"] = shortened
                tex = _replace_summary(tex, shortened)
                log.append({"section": "summary", "action": "trimmed for the One-Page Rule",
                            "after": shortened})
                progressed = True
            else:
                trim_stage = 1

        if not progressed and trim_stage == 1:
            for bullet_id, key in (("experience-bullet-1", "bullet_1"), ("experience-bullet-2", "bullet_2")):
                shortened = _shorten(state[key], 170)
                if shortened != state[key]:
                    state[key] = shortened
                    tex = _replace_bullet(tex, bullet_id, shortened)
                    log.append({"section": bullet_id, "action": "trimmed for the One-Page Rule",
                                "after": shortened})
                    progressed = True
            if not progressed:
                trim_stage = 2

        if not progressed and trim_stage == 2:
            if state["skill_additions"]:
                dropped = state["skill_additions"].pop()
                tex = _insert_additional_skills(tex, state["skill_additions"])
                log.append({"section": "skills",
                            "action": f"dropped '{dropped['skill']}' for the One-Page Rule"})
                progressed = True

        if not progressed:
            break

        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex)
        pdf_path = _compile(tex_path, output_dir)
        pages = _page_count(pdf_path)

    if pages > 1:
        raise RuntimeError(
            f"Resume for this job is still {pages} pages after {attempts} trim "
            "attempts -- needs manual intervention (see PLAN.md's One-Page Rule)."
        )
    return tex, pdf_path


# ---------------------------------------------------------------------------
# LLM call: the only creative-writing step (summary / bullets / swap bullet)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the resume-tailoring step of a job search agent. \
You are given ONE job posting, its already-computed fit analysis (weak \
points, aligned skills, and -- if applicable -- which resume project is \
weak and which real portfolio project should replace it), and the \
candidate's real resume text. Your job is ONLY to rewrite pieces of prose, \
grounded strictly in what's real:

1. A new Professional Summary (2-4 sentences) tailored to this job.
2. Two rewritten experience bullets (the ones given to you), reframed to \
emphasize what this job cares about.
3. If a project swap is indicated below, one resume-style bullet for the \
NEW project (1-2 sentences, in the same style as the existing project \
bullets), based ONLY on that project's real description given to you.

Hard rules, no exceptions:
1. Never invent a company, job title, employer, degree, skill, project, or \
metric that isn't already given to you below.
2. Any number in the ORIGINAL bullet text (percentages, scores, latency, \
counts) must appear, unchanged, in your rewritten version -- you may \
reframe wording and emphasis, but never the underlying facts and metrics, \
and never introduce a new number that wasn't already there.
3. If asked to write a bullet for a swapped-in project, only use numbers \
that are literally present in that project's given description -- do not \
invent a new metric for it.
4. Do NOT add skills to the summary/bullets that are listed as "genuine \
gaps" below -- those are honest gaps, never claimed.
5. Output ONLY a single valid JSON object. No markdown code fences, no \
commentary before or after, no trailing commas.

Respond with EXACTLY this JSON shape:
{
  "new_summary": "<string>",
  "bullet_1_new": "<string, rewritten version of bullet 1>",
  "bullet_2_new": "<string, rewritten version of bullet 2>",
  "swapped_project_bullet": "<string, or null if no swap is indicated>",
  "reasoning": {
    "summary": "<why you emphasized what you did>",
    "bullet_1": "<why>",
    "bullet_2": "<why>",
    "swapped_project_bullet": "<why, or null>"
  }
}"""


def _build_user_prompt(job: dict, fit_analysis: dict, profile: dict,
                        bullet_1: str, bullet_2: str, swap_project: dict) -> str:
    core = fit_analysis.get("core_skills", {})
    missing_evidenced = core.get("missing_evidenced", [])
    missing_evidenced_str = ", ".join(
        f"{m['skill']} ({m.get('evidence', '')})" if isinstance(m, dict) else str(m)
        for m in missing_evidenced
    ) or "(none)"

    if swap_project:
        swap_section = f"""A project swap IS indicated for this job. Use ONLY these real facts about the new project (nothing invented):
Name: {swap_project['name']}
Domain: {swap_project['domain']}
Tech stack: {', '.join(swap_project['tech_stack'])}
Description: {swap_project['description']}
Write one resume-style bullet (1-2 sentences) for this project, matching the style of the existing project bullets in the resume below."""
    else:
        swap_section = "No project swap is indicated for this job -- set swapped_project_bullet to null."

    return f"""JOB POSTING
Title: {job['title']}
Company: {job['company']}
Domain: {job['industry_domain']}
Description: {job['description']}

FIT ANALYSIS (already computed by an earlier step -- do not re-decide any verdicts, just use this to decide what to emphasize)
Relevant Experience: {fit_analysis['relevant_experience']['status']} -- {fit_analysis['relevant_experience']['explanation']}
Seniority: {fit_analysis['seniority']['status']} -- {fit_analysis['seniority']['explanation']}
Education: {fit_analysis['education']['status']} -- {fit_analysis['education']['explanation']}
Aligned skills: {', '.join(core.get('aligned', [])) or '(none)'}
Missing but evidenced elsewhere (already being added to the Skills section separately -- fine to reference in prose too): {missing_evidenced_str}
Genuine gaps (never claim these anywhere): {', '.join(core.get('genuine_gap', [])) or '(none)'}

CURRENT RESUME (plain text, for context/style)
{profile['resume_plaintext']}

BULLET 1 TO REWRITE (from the current role at Meridian Health Analytics):
"{bullet_1}"

BULLET 2 TO REWRITE (from the current role at Meridian Health Analytics):
"{bullet_2}"

{swap_section}

Now produce the JSON object described in your instructions."""


CORRECTION_PROMPT_TEMPLATE = """One or more of your rewrites failed a numeric-accuracy check:
{issues}

Re-send the FULL JSON object again, unchanged except: fix the flagged \
field(s) so every number in your rewrite matches the real source numbers \
exactly (no dropped, changed, or invented numbers). Output ONLY the \
corrected JSON object."""


def _propose_edits(job, fit_analysis, profile, bullet_1, bullet_2, swap_project, revision_feedback=None) -> dict:
    user_prompt = _build_user_prompt(job, fit_analysis, profile, bullet_1, bullet_2, swap_project)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    if revision_feedback:
        messages.append({
            "role": "user",
            "content": f"Human reviewer feedback from a prior round -- apply it now: {revision_feedback}",
        })

    raw = chat(messages=messages, temperature=0.3, response_format={"type": "json_object"})
    proposal = _extract_json(raw)

    issues = []
    if not _same_numbers(bullet_1, proposal.get("bullet_1_new") or ""):
        issues.append("bullet_1_new: numbers must exactly match the original bullet's numbers")
    if not _same_numbers(bullet_2, proposal.get("bullet_2_new") or ""):
        issues.append("bullet_2_new: numbers must exactly match the original bullet's numbers")
    if swap_project and proposal.get("swapped_project_bullet"):
        if not _no_new_numbers(swap_project["description"], proposal["swapped_project_bullet"]):
            issues.append("swapped_project_bullet: contains a number not present in the real project description")
    if not _no_new_numbers(profile["resume_plaintext"], proposal.get("new_summary") or ""):
        issues.append("new_summary: contains a number not present anywhere in the real resume")

    if issues:
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": CORRECTION_PROMPT_TEMPLATE.format(issues="\n".join(issues))})
        try:
            corrected_raw = chat(messages=messages, temperature=0.2, response_format={"type": "json_object"})
            corrected = _extract_json(corrected_raw)
            for field in ("new_summary", "bullet_1_new", "bullet_2_new", "swapped_project_bullet", "reasoning"):
                if field in corrected:
                    proposal[field] = corrected[field]
        except (ValueError, json.JSONDecodeError):
            pass  # fall through -- caller applies its own per-field fallback

    return proposal


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def tailor_resume(job: dict, fit_analysis: dict, profile: dict, revision_feedback: str = None) -> dict:
    """
    Tailors resume.tex for ONE job, recompiles to a verified one-page PDF,
    and returns {"job_id", "tex_path", "pdf_path", "before_pdf_path", "change_log"}.

    revision_feedback: optional human-review comment from a rework round.
    Unused by this workstream, but Stage 4 (Human Review + Memory) needs
    to "feed rejection comments back into tailoring.py for another pass"
    per PLAN.md -- this parameter is that hook, so Stage 4 doesn't need to
    change this function's signature.
    """
    job_id = job["job_id"]
    job_dir = os.path.join(REPO_ROOT, "outputs", job_id)
    os.makedirs(job_dir, exist_ok=True)

    with open(RESUME_TEX_PATH, encoding="utf-8") as f:
        tex = f.read()
    resume_text_lower = tex.lower()

    bullet_1_orig = _extract_bullet(tex, "experience-bullet-1")
    bullet_2_orig = _extract_bullet(tex, "experience-bullet-2")
    summary_orig = _extract_summary(tex)

    project_swap = fit_analysis.get("project_swap") or {}
    swap_recommended = bool(project_swap.get("recommended"))
    swap_project = None
    if swap_recommended:
        swap_project = next(
            (p for p in profile["portfolio_projects"]
             if p["name"].strip().lower() == project_swap["better_portfolio_project"].strip().lower()),
            None,
        )
        if swap_project is None:
            # Stage 2 already fact-checked this name against data/portfolio.txt
            # (see fit_analysis.py's _validate_project_swap) -- this should
            # never happen, but fail loudly rather than silently skip it.
            raise ValueError(
                f"project_swap names '{project_swap['better_portfolio_project']}' "
                "but no such project exists in data/portfolio.txt."
            )

    proposal = _propose_edits(job, fit_analysis, profile, bullet_1_orig, bullet_2_orig,
                               swap_project, revision_feedback)

    change_log = []

    # --- Professional Summary ---
    new_summary = (proposal.get("new_summary") or "").strip()
    if new_summary and _no_new_numbers(profile["resume_plaintext"], new_summary):
        tex = _replace_summary(tex, new_summary)
        change_log.append({
            "section": "summary", "before": summary_orig, "after": new_summary,
            "citation": "fit_analysis relevant_experience/seniority/education/core_skills",
            "reason": (proposal.get("reasoning") or {}).get("summary", ""),
        })
        current_summary = new_summary
    else:
        change_log.append({
            "section": "summary", "before": summary_orig, "after": summary_orig,
            "citation": "kept original -- rewrite failed the anti-fabrication numeric check",
            "reason": "LLM proposal introduced a number not traceable to the real resume.",
        })
        current_summary = summary_orig

    # --- Experience bullets (exactly 2) ---
    bullet_state = {}
    for bullet_id, orig, proposed_key in (
        ("experience-bullet-1", bullet_1_orig, "bullet_1_new"),
        ("experience-bullet-2", bullet_2_orig, "bullet_2_new"),
    ):
        new_text = (proposal.get(proposed_key) or "").strip()
        if new_text and _same_numbers(orig, new_text):
            tex = _replace_bullet(tex, bullet_id, new_text)
            change_log.append({
                "section": bullet_id, "before": orig, "after": new_text,
                "citation": "fit_analysis relevant_experience / core_skills",
                "reason": (proposal.get("reasoning") or {}).get(
                    "bullet_1" if bullet_id.endswith("1") else "bullet_2", ""),
            })
            bullet_state[bullet_id.replace("experience-", "").replace("-", "_")] = new_text
        else:
            change_log.append({
                "section": bullet_id, "before": orig, "after": orig,
                "citation": "kept original -- rewrite failed the anti-fabrication numeric check",
                "reason": "LLM proposal dropped, changed, or invented a metric relative to the original bullet.",
            })
            bullet_state[bullet_id.replace("experience-", "").replace("-", "_")] = orig

    # --- Skills: surface-form alignment + evidenced additions (deterministic) ---
    skill_additions = _skills_to_add(fit_analysis, resume_text_lower, profile)
    if skill_additions:
        tex = _insert_additional_skills(tex, skill_additions)
        for addition in skill_additions:
            change_log.append({
                "section": "skills", "before": "(not listed)", "after": addition["skill"],
                "citation": addition["citation"], "reason": "Evidenced and relevant to this job's required skills.",
            })

    genuine_gaps = (fit_analysis.get("core_skills") or {}).get("genuine_gap") or []
    for gap in genuine_gaps:
        change_log.append({
            "section": "skills (not applied)", "before": "(not listed)", "after": "(not added)",
            "citation": "fit_analysis core_skills.genuine_gap", "reason": f"'{gap}' is a genuine gap -- no evidence anywhere in the profile, never added.",
        })

    # --- Project swap ---
    if swap_recommended and swap_project:
        swap_bullet = (proposal.get("swapped_project_bullet") or "").strip()
        if not swap_bullet or not _no_new_numbers(swap_project["description"], swap_bullet):
            # Deterministic fallback: a plain, truncated version of the
            # project's own real description -- guaranteed to contain no
            # invented numbers since it's the source text itself.
            swap_bullet = _shorten(swap_project["description"], 220)
        tex = _replace_project(tex, project_swap["weak_resume_project"], swap_project, swap_bullet)
        change_log.append({
            "section": "project_swap",
            "before": project_swap["weak_resume_project"],
            "after": swap_project["name"],
            "citation": "fit_analysis.project_swap (Stage 2 fact-checked)",
            "reason": project_swap.get("reasoning", ""),
        })
    else:
        change_log.append({
            "section": "project_swap", "before": "(no swap)", "after": "(no swap)",
            "citation": "fit_analysis.project_swap",
            "reason": project_swap.get("reasoning", "Current on-resume projects are already optimal for this job."),
        })

    # --- Recompile + One-Page Rule ---
    tex_path = os.path.join(job_dir, "resume_tailored.tex")
    state = {"summary": current_summary, **bullet_state, "skill_additions": skill_additions}
    tex, pdf_path = _enforce_one_page(tex, tex_path, job_dir, state, change_log)

    final_pdf_path = os.path.join(job_dir, "resume_after.pdf")
    if os.path.abspath(pdf_path) != os.path.abspath(final_pdf_path):
        shutil.copyfile(pdf_path, final_pdf_path)
        os.remove(pdf_path)  # drop the redundant raw pdflatex-named copy

    before_pdf_path = os.path.join(job_dir, "resume_before.pdf")
    shutil.copyfile(RESUME_PDF_PATH, before_pdf_path)

    with open(os.path.join(job_dir, "change_log.json"), "w", encoding="utf-8") as f:
        json.dump(change_log, f, indent=2)
    with open(os.path.join(job_dir, "change_log.md"), "w", encoding="utf-8") as f:
        f.write(_format_change_log(job, change_log))

    return {
        "job_id": job_id,
        "tex_path": tex_path,
        "pdf_path": final_pdf_path,
        "before_pdf_path": before_pdf_path,
        "change_log": change_log,
    }


def _format_change_log(job: dict, change_log: list) -> str:
    lines = [f"# Change Log: {job['title']} @ {job['company']}  [{job['job_id']}]\n"]
    for entry in change_log:
        lines.append(f"## {entry['section']}")
        if "before" in entry:
            lines.append(f"- **Before:** {entry['before']}")
        if "after" in entry:
            lines.append(f"- **After:** {entry['after']}")
        lines.append(f"- **Citation:** {entry['citation']}")
        lines.append(f"- **Reason:** {entry['reason']}\n")
    return "\n".join(lines)


if __name__ == "__main__":
    outputs_dir = os.path.join(REPO_ROOT, "outputs")
    with open(os.path.join(outputs_dir, "ranked_jobs.json"), encoding="utf-8") as f:
        ranked = json.load(f)
    top3_job_ids = ranked["top3_job_ids"]

    all_jobs = {j["job_id"]: j for j in load_jobs(os.path.join(REPO_ROOT, "data", "jobs.csv"))}
    profile = load_full_profile()

    for job_id in top3_job_ids:
        job = all_jobs[job_id]
        with open(os.path.join(outputs_dir, job_id, "fit_analysis.json"), encoding="utf-8") as f:
            fit_analysis = json.load(f)

        print(f"Tailoring resume for [{job_id}] {job['title']} @ {job['company']} ...")
        result = tailor_resume(job, fit_analysis, profile)
        print(f"  -> {result['pdf_path']}")
        print(f"  -> {len(result['change_log'])} change-log entries "
              f"(outputs/{job_id}/change_log.json)")
