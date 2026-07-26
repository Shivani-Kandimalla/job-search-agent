"""
Persistent agent memory (Section 3.5 of the assignment).

The review pause is the only place where the candidate can state a fact
that exists in NO input file ("Add GraphQL, I know it"). Those facts are
written here, to `memory/memory.json`, with their provenance, and loaded
again at startup by `profile.load_full_profile()` so they count as
evidence in every later run.

Schema (finalizes the Foundation workstream's sketch in README.md -- the
two top-level keys are unchanged, so `profile.memory_skills()` keeps
working; the per-entry fields are the part this workstream pinned down):

    {
      "skills_learned": [
        {
          "skill": "GraphQL",
          "source": "stated by candidate",
          "review_round": 1,
          "job_id": "J18",              # which resume was under review
          "comment": "<verbatim reviewer comment the fact came from>",
          "timestamp": "2026-07-25T14:03:11"
        }
      ],
      "other_facts": [
        { "fact": "...", "source": ..., "review_round": ..., "job_id": ...,
          "comment": ..., "timestamp": ... }
      ]
    }

Scope rule from the assignment: "Skills and candidate facts only." Anything
that is a *tailoring instruction* ("make the summary shorter") is feedback
for the rework round, not a fact about the candidate, and is never written
here -- see human_review.py's extraction step for how the two are split.
"""

import json
import os
from datetime import datetime

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MEMORY_PATH = os.path.join(REPO_ROOT, "memory", "memory.json")

EMPTY_MEMORY = {"skills_learned": [], "other_facts": []}


def load_memory(path: str = MEMORY_PATH) -> dict:
    """Load-at-startup entry point. A missing/corrupt file is not fatal --
    an empty memory is a valid state (it's what the very first run sees)."""
    if not os.path.isfile(path):
        return json.loads(json.dumps(EMPTY_MEMORY))
    try:
        with open(path, encoding="utf-8") as f:
            memory = json.load(f)
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(EMPTY_MEMORY))
    memory.setdefault("skills_learned", [])
    memory.setdefault("other_facts", [])
    return memory


def save_memory(memory: dict, path: str = MEMORY_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)
        f.write("\n")


def known_skills(memory: dict = None, path: str = MEMORY_PATH) -> list:
    memory = memory if memory is not None else load_memory(path)
    return [entry["skill"] for entry in memory.get("skills_learned", [])]


def _already_known(skill: str, memory: dict, master_skills: list) -> bool:
    """A skill is only worth remembering if the agent didn't already have
    it -- re-writing something that's already in the master skills list
    would just pad the memory file."""
    skill_lower = skill.strip().lower()
    if not skill_lower:
        return True
    existing = [s.lower() for s in known_skills(memory)]
    if skill_lower in existing:
        return True
    return any(skill_lower == m.strip().lower() for m in master_skills or [])


def add_skill(skill: str, job_id: str, review_round: int, comment: str,
              memory: dict = None, master_skills: list = None,
              path: str = MEMORY_PATH, save: bool = True) -> dict:
    """Writes one candidate-stated skill to memory with full provenance.

    Returns {"written": bool, "entry": dict|None, "reason": str} -- the
    caller logs this, so a skipped duplicate is visible in the review log
    and in the trace rather than silently disappearing.
    """
    memory = memory if memory is not None else load_memory(path)
    skill = (skill or "").strip()

    if not skill:
        return {"written": False, "entry": None, "reason": "empty skill string"}
    if _already_known(skill, memory, master_skills or []):
        return {"written": False, "entry": None,
                "reason": f"'{skill}' is already evidenced (master skills list or existing memory) -- not re-written"}

    entry = {
        "skill": skill,
        "source": "stated by candidate",
        "review_round": review_round,
        "job_id": job_id,
        "comment": comment,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    memory["skills_learned"].append(entry)
    if save:
        save_memory(memory, path)
    return {"written": True, "entry": entry, "reason": "new candidate-stated skill"}


def add_other_fact(fact: str, job_id: str, review_round: int, comment: str,
                   memory: dict = None, path: str = MEMORY_PATH,
                   save: bool = True) -> dict:
    """Non-skill candidate facts (e.g. "I'm open to hybrid roles in
    Seattle"). Same provenance fields as a skill entry."""
    memory = memory if memory is not None else load_memory(path)
    fact = (fact or "").strip()
    if not fact:
        return {"written": False, "entry": None, "reason": "empty fact string"}

    existing = [e.get("fact", "").strip().lower() for e in memory.get("other_facts", [])]
    if fact.lower() in existing:
        return {"written": False, "entry": None, "reason": "duplicate fact -- already in memory"}

    entry = {
        "fact": fact,
        "source": "stated by candidate",
        "review_round": review_round,
        "job_id": job_id,
        "comment": comment,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    memory["other_facts"].append(entry)
    if save:
        save_memory(memory, path)
    return {"written": True, "entry": entry, "reason": "new candidate-stated fact"}


def citation_for(skill: str, memory: dict = None, path: str = MEMORY_PATH) -> str:
    """Evidence-Rule citation string for a memory-learned skill, e.g.
    "memory.json (stated by candidate, review round 1, while reviewing
    J18)". Used by the change log so a memory-sourced resume edit cites
    its source like every other edit does."""
    memory = memory if memory is not None else load_memory(path)
    for entry in memory.get("skills_learned", []):
        if entry["skill"].strip().lower() == (skill or "").strip().lower():
            return (f"memory.json (stated by candidate, review round "
                    f"{entry['review_round']}, while reviewing {entry['job_id']})")
    return "memory.json"


def reset(path: str = MEMORY_PATH) -> None:
    """Wipes memory back to the empty schema. Used before a clean
    end-to-end demo run (PLAN.md: 'Reset memory, run the entire pipeline
    fresh end-to-end')."""
    save_memory(json.loads(json.dumps(EMPTY_MEMORY)), path)


if __name__ == "__main__":
    memory = load_memory()
    print(f"memory/memory.json -> {len(memory['skills_learned'])} learned skills, "
          f"{len(memory['other_facts'])} other facts")
    for entry in memory["skills_learned"]:
        print(f"  - {entry['skill']}  ({entry['source']}, review round "
              f"{entry['review_round']}, job {entry['job_id']}, {entry['timestamp']})")
    for entry in memory["other_facts"]:
        print(f"  - {entry['fact']}  ({entry['source']}, review round "
              f"{entry['review_round']}, job {entry['job_id']}, {entry['timestamp']})")
