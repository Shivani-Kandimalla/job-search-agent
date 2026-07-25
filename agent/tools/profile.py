"""
Shared profile-loading helpers used by the Scoring Tool, Fit Analysis Tool,
and (later) the Tailoring Tool. Centralizing this here means every tool
reads the resume, portfolio, preferences, and memory the exact same way.

None of this makes an LLM call — it's pure file I/O and light parsing.
"""

import json
import os
import re


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _path(*parts):
    return os.path.join(REPO_ROOT, *parts)


def load_resume_text(path: str = None) -> str:
    """Returns the raw .tex source. Good enough for keyword/skill matching
    purposes -- the plain-English words (skills, project names, bullets)
    are still readable inside the LaTeX markup."""
    path = path or _path("resume", "resume.tex")
    with open(path, encoding="utf-8") as f:
        return f.read()


def resume_plaintext(tex_text: str = None) -> str:
    """Best-effort strip of resume.tex down to readable plain text, for
    feeding to the LLM in Fit Analysis / Tailoring prompts. This is a
    heuristic regex pass, not a real LaTeX parser -- good enough to make
    section headers, bullets, and dates legible; not meant to be pixel
    perfect."""
    text = tex_text if tex_text is not None else load_resume_text()

    text = re.sub(r"(?<!\\)%.*", "", text)  # strip comments (not \%)
    text = text.replace("\\%", "%")

    # \resumeEntry{a}{b}{c}{d} is a custom 4-arg macro (title/company on one
    # line, date/location on the next) -- the generic single-arg peeling
    # loop below doesn't know its structure and would smash all 4 args
    # together with no separator, so handle it explicitly first.
    text = re.sub(
        r"\\resumeEntry\s*\{([^{}]*)\}\s*\{([^{}]*)\}\s*\{([^{}]*)\}\s*\{([^{}]*)\}",
        r"\n\1 -- \2\n\3 -- \4",
        text,
    )

    text = re.sub(r"\\section\{([^{}]*)\}", r"\n\n== \1 ==\n", text)
    text = re.sub(r"\\resumeItem\{", r"\\item{", text)  # normalize for the peel loop below
    text = text.replace("\\resumeItemListStart", "").replace("\\resumeItemListEnd", "")
    text = text.replace("\\resumeEntryListStart", "").replace("\\resumeEntryListEnd", "")
    text = re.sub(r"\\item\s*", "\n- ", text)

    # Peel nested \command{...} wrappers down to their inner text, a few passes
    # to handle nesting like \textbf{\small{...}}.
    for _ in range(6):
        text = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?\{([^{}]*)\}", r"\2", text)

    text = text.replace("\\\\", "\n")
    text = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", "", text)  # remaining bare commands
    text = text.replace("{", "").replace("}", "")
    text = text.replace("$|$", "|")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    # Drop everything before the header/name block and the trailing
    # "document" artifact left over from \end{document} -- pure preamble
    # noise (package names, spacing tweaks) that isn't useful to an LLM.
    header_match = re.search(r"\n Jordan Ellis \n", text)
    if header_match:
        text = text[header_match.start():]
    text = re.sub(r"\n\s*document\s*$", "", text)

    return text.strip()


def load_portfolio_text(path: str = None) -> str:
    path = path or _path("data", "portfolio.txt")
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_portfolio_projects(path: str = None) -> list:
    """Parses data/portfolio.txt into structured project dicts:
    {name, on_resume (bool), domain, tech_stack (list[str]), description}

    Relies on the file's consistent format (each project is a
    "PROJECT N: <name>  [ON RESUME]" or "[PORTFOLIO ONLY]" header line,
    followed by "Domain/Industry:", "Tech stack:", "Description:" lines).
    """
    text = load_portfolio_text(path)
    blocks = re.split(r"-{5,}", text)

    projects = []
    header_re = re.compile(
        r"PROJECT\s+\d+:\s*(?P<name>.+?)\s*\[(?P<tag>ON RESUME|PORTFOLIO ONLY)\]"
    )
    domain_re = re.compile(r"Domain/Industry:\s*(?P<domain>.+)")
    tech_re = re.compile(r"Tech stack:\s*(?P<tech>.+)")
    desc_re = re.compile(r"Description:\s*(?P<desc>.+?)(?=\n[A-Z][a-z]+/?[A-Za-z]*:|\Z)", re.DOTALL)

    for block in blocks:
        header_match = header_re.search(block)
        if not header_match:
            continue
        domain_match = domain_re.search(block)
        tech_match = tech_re.search(block)
        desc_match = desc_re.search(block)

        tech_stack = []
        if tech_match:
            tech_stack = [t.strip() for t in tech_match.group("tech").split(",") if t.strip()]

        description = ""
        if desc_match:
            description = " ".join(desc_match.group("desc").split())

        projects.append({
            "name": header_match.group("name").strip(),
            "on_resume": header_match.group("tag") == "ON RESUME",
            "domain": domain_match.group("domain").strip() if domain_match else "",
            "tech_stack": tech_stack,
            "description": description,
        })

    return projects


def split_skills(skills_str: str) -> list:
    """Splits a comma-separated required_skills string on top-level commas
    only, so a skill like 'computer vision (YOLO, Segment Anything)' stays
    one item instead of being torn in two at the comma inside the
    parentheses."""
    parts, current, depth = [], [], 0
    for ch in skills_str or "":
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def extract_degree_fields(resume_plaintext_str: str) -> list:
    """Pulls out field-of-study strings from lines like 'M.S. in Data
    Science, GPA 3.8/4.0' or 'B.S. in Statistics' in the resume's plain
    text, e.g. -> ['Data Science', 'Statistics'].
    """
    matches = re.findall(
        r"(?:B\.?S\.?|M\.?S\.?|Ph\.?D\.?|B\.?A\.?|M\.?A\.?)\s+in\s+([A-Za-z][A-Za-z &]+)",
        resume_plaintext_str,
    )
    fields = []
    for m in matches:
        field = re.split(r",", m)[0].strip()
        if field:
            fields.append(field)
    return fields


def load_persona_preferences(path: str = None) -> dict:
    path = path or _path("data", "persona_preferences.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_master_skills(path: str = None) -> list:
    return load_persona_preferences(path).get("master_skills_list", [])


def load_candidate_years(path: str = None) -> int:
    return load_persona_preferences(path).get("years_of_experience", 0)


def load_memory(path: str = None) -> dict:
    path = path or _path("memory", "memory.json")
    if not os.path.isfile(path):
        return {"skills_learned": [], "other_facts": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def memory_skills(memory: dict) -> list:
    """Flat list of skill names the candidate has taught the agent via the
    human-review pause, e.g. ["GraphQL"]."""
    return [entry["skill"] for entry in memory.get("skills_learned", [])]


def load_full_profile() -> dict:
    """Convenience bundle of everything Scoring / Fit Analysis / Tailoring
    need to reason about "the whole profile", not just the resume."""
    preferences = load_persona_preferences()
    memory = load_memory()
    resume_text = load_resume_text()
    resume_plain = resume_plaintext(resume_text)
    return {
        "resume_text": resume_text,
        "resume_plaintext": resume_plain,
        "degree_fields": extract_degree_fields(resume_plain),
        "portfolio_text": load_portfolio_text(),
        "portfolio_projects": parse_portfolio_projects(),
        "master_skills": preferences.get("master_skills_list", []),
        "candidate_years": preferences.get("years_of_experience", 0),
        "candidate_name": preferences.get("candidate_name", ""),
        "preferences": preferences.get("preferences", {}),
        "memory": memory,
        "memory_skills": memory_skills(memory),
    }


if __name__ == "__main__":
    profile = load_full_profile()
    print("--- resume_plaintext preview ---")
    print(profile["resume_plaintext"])
    print("--- end preview ---\n")
    print(f"Candidate: {profile['candidate_name']}, {profile['candidate_years']} years experience")
    print(f"Master skills ({len(profile['master_skills'])}): {profile['master_skills']}")
    print(f"Memory-learned skills: {profile['memory_skills']}")
    print(f"\nPortfolio projects ({len(profile['portfolio_projects'])}):")
    for p in profile["portfolio_projects"]:
        tag = "ON RESUME" if p["on_resume"] else "portfolio-only"
        print(f"  - {p['name']} [{tag}] | domain={p['domain']} | tech={p['tech_stack']}")
