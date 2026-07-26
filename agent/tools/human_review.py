"""
Human-in-the-Loop Review + Memory (Section 3.5 of the assignment) -- the
agent's ONE and ONLY pause.

Flow implemented here, per job in the Top 3:

    print the citation-backed change log  ->  reviewer types approve /
    reject + comments  ->  (on reject) extract any candidate FACTS stated
    in the comment, write them to memory/memory.json with provenance, then
    re-run the Tailoring Tool with the comment as revision feedback  ->
    show the new change log  ->  repeat, capped at 2 revision rounds.

Three things this module deliberately gets right, because they are what
Section 3.5 is actually testing:

1. **Facts vs. instructions.** "Add GraphQL, I know it" states a fact
   about the candidate and belongs in memory forever. "The summary is too
   generic" is feedback about this one edit and must NOT be written to
   memory. An LLM call does the split (it's a language-understanding
   judgment, not a rule); a code-level guard then throws away any
   "extracted" skill whose text doesn't literally appear in the reviewer's
   own comment, so the model can't invent a skill on the candidate's
   behalf.

2. **Immediate, same-run carry-over.** A skill learned while reviewing job
   1 is re-applied to jobs 2 and 3 in the same run, without the reviewer
   repeating it: before each job is reviewed, its fit analysis's
   deterministic `skill_buckets` are recomputed against the CURRENT memory
   (`refresh_fit_analysis_with_memory`), and if that moves a required
   skill out of `genuine_gap`, the job's resume is re-tailored so the
   newly-evidenced skill actually lands on the page, cited to memory.

3. **Approval gates the finalization.** Cover letters (and the final PDF
   copies) are only produced for jobs the reviewer approved -- that's the
   only gate in the whole pipeline, and there are no others.

Run it standalone (from the repo root, after tailoring has produced the 3
change logs):

    python agent/tools/human_review.py                 # interactive
    python agent/tools/human_review.py --reset-memory  # start from empty memory
    python agent/tools/human_review.py --script demo_review_script.json
"""

import argparse
import json
import os
import re

import cover_letter as cover_letter_tool
import memory_store
from fit_analysis import _extract_json, classify_required_skills
from filtering import load_jobs
from llm_client import chat
from profile import load_full_profile
from tailoring import tailor_resume

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUTPUTS_DIR = os.path.join(REPO_ROOT, "outputs")

MAX_REVISION_ROUNDS = 2  # assignment: "maximum 2 revision rounds"


# ---------------------------------------------------------------------------
# Console presentation
# ---------------------------------------------------------------------------

def format_change_log(job: dict, change_log: list) -> str:
    """The exact thing the reviewer sees: every edit as a before/after pair
    with its citation and reason (Section 3.5: 'Present the Top 3 change
    logs, including project swaps, with citations')."""
    lines = [
        "=" * 78,
        f"CHANGE LOG -- [{job['job_id']}] {job['title']} @ {job['company']}",
        "=" * 78,
    ]
    for entry in change_log:
        section = entry.get("section", "?")
        lines.append(f"\n--- {section} ---")
        if "before" in entry:
            lines.append(f"  BEFORE  : {entry['before']}")
        if "after" in entry:
            lines.append(f"  AFTER   : {entry['after']}")
        if entry.get("action"):
            lines.append(f"  ACTION  : {entry['action']}")
        if entry.get("citation"):
            lines.append(f"  CITATION: {entry['citation']}")
        if entry.get("reason"):
            lines.append(f"  REASON  : {entry['reason']}")
    return "\n".join(lines)


def _prompt(input_fn, text: str) -> str:
    try:
        return (input_fn(text) or "").strip()
    except EOFError:
        return ""


def prompt_decision(job: dict, input_fn, round_no: int) -> tuple:
    """Console decision for one resume. Returns (decision, comment) where
    decision is 'approve' or 'reject'."""
    while True:
        answer = _prompt(
            input_fn,
            f"\n[{job['job_id']}] Review round {round_no} -- approve this tailored resume? "
            f"Type 'approve' or 'reject': ",
        ).lower()
        if answer.startswith("a"):
            return "approve", ""
        if answer.startswith("r"):
            comment = _prompt(
                input_fn,
                "  Comments (what should change? mention any skills you have that are "
                "missing -- the agent will remember them): ",
            )
            return "reject", comment
        print("  Please type 'approve' or 'reject'.")


# ---------------------------------------------------------------------------
# Fact extraction from review comments (LLM call + code-level guard)
# ---------------------------------------------------------------------------

FACT_EXTRACTION_SYSTEM_PROMPT = """You are the memory step of a job search agent. A human reviewer has \
just rejected a tailored resume and written a comment. Split that comment \
into two different kinds of content:

1. FACTS ABOUT THE CANDIDATE -- things that are true about the person \
regardless of which job is being applied to, and that the agent should \
remember forever. Most often a skill or technology the candidate says they \
know but that isn't in their files yet ("add GraphQL, I know it"). \
Occasionally a non-skill personal fact ("I'm open to hybrid roles in \
Seattle").

2. TAILORING INSTRUCTIONS -- feedback about THIS resume edit only ("the \
summary is too generic", "keep the healthcare detail", "shorten the second \
bullet"). These must never be remembered as facts.

Hard rules, no exceptions:
1. Only list a skill if the reviewer's comment actually says the candidate \
knows/has/used it. Never infer a skill from a job posting, from the resume, \
or from the fact that they mentioned a topic.
2. Copy skill names exactly as the reviewer wrote them (same spelling and \
capitalisation). Never expand, translate, or normalise them.
3. If the comment contains no candidate facts at all, return empty lists -- \
that is a perfectly normal answer.
4. Never invent anything that isn't in the comment.
5. Output ONLY a single valid JSON object. No markdown code fences, no \
commentary before or after, no trailing commas.

Respond with EXACTLY this JSON shape:
{
  "skills": ["<skill exactly as written by the reviewer>", "..."],
  "other_facts": ["<non-skill candidate fact, quoted closely from the comment>", "..."],
  "tailoring_instructions": ["<the feedback about this specific edit>", "..."],
  "reasoning": "<1-2 sentences on why you classified each part the way you did>"
}"""


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _stated_in_comment(skill: str, comment: str) -> bool:
    """Evidence Rule, applied to memory: the agent may only remember a
    skill the reviewer literally typed. This is what stops a model that
    'helpfully' pattern-matches the job posting from writing a skill the
    candidate never claimed into permanent memory."""
    return bool(skill.strip()) and _normalise(skill) in _normalise(comment)


def _fact_supported_by_comment(fact: str, comment: str, threshold: float = 0.6) -> bool:
    """Non-skill facts are paraphrases, so an exact-substring test is too
    strict -- require most of the fact's content words to come from the
    reviewer's own comment instead."""
    fact_tokens = [t for t in _normalise(fact).split() if len(t) > 2]
    if not fact_tokens:
        return False
    comment_tokens = set(_normalise(comment).split())
    hits = sum(1 for t in fact_tokens if t in comment_tokens)
    return hits / len(fact_tokens) >= threshold


def extract_facts(comment: str, profile: dict) -> dict:
    """Returns {"skills", "other_facts", "tailoring_instructions",
    "reasoning", "rejected"} -- `rejected` lists anything the model
    proposed that failed the literal-mention guard, so the review log and
    the trace show the guard doing its job."""
    empty = {"skills": [], "other_facts": [], "tailoring_instructions": [],
             "reasoning": "", "rejected": []}
    if not (comment or "").strip():
        return empty

    messages = [
        {"role": "system", "content": FACT_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": f"""REVIEWER COMMENT (verbatim):
"{comment}"

For context, the candidate's already-known skills (do NOT re-list these unless the reviewer explicitly restates them):
{', '.join(profile['master_skills'])}
Already in memory: {', '.join(profile['memory_skills']) or '(none yet)'}

Now produce the JSON object described in your instructions."""},
    ]

    try:
        raw = chat(messages=messages, temperature=0.1, response_format={"type": "json_object"})
        parsed = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        # A failed extraction must not lose the reviewer's feedback: the raw
        # comment still drives the rework, it just teaches nothing new.
        return {**empty, "tailoring_instructions": [comment],
                "reasoning": "Fact extraction returned unparseable output; the comment was "
                             "still applied verbatim as tailoring feedback."}

    skills, other_facts, rejected = [], [], []
    for skill in parsed.get("skills") or []:
        skill = str(skill).strip()
        if _stated_in_comment(skill, comment):
            skills.append(skill)
        else:
            rejected.append({"proposed": skill, "kind": "skill",
                             "reason": "not literally stated in the reviewer's comment"})

    for fact in parsed.get("other_facts") or []:
        fact = str(fact).strip()
        if _fact_supported_by_comment(fact, comment):
            other_facts.append(fact)
        else:
            rejected.append({"proposed": fact, "kind": "other_fact",
                             "reason": "not supported by the reviewer's comment"})

    return {
        "skills": skills,
        "other_facts": other_facts,
        "tailoring_instructions": [str(i) for i in (parsed.get("tailoring_instructions") or [])],
        "reasoning": parsed.get("reasoning", ""),
        "rejected": rejected,
    }


def write_facts_to_memory(facts: dict, job_id: str, review_round: int,
                          comment: str, profile: dict) -> list:
    """Persists the extracted facts and refreshes the in-run profile so the
    new knowledge is usable immediately (same run, remaining jobs included).
    Returns one log entry per attempted write."""
    writes = []
    memory = memory_store.load_memory()

    for skill in facts.get("skills", []):
        result = memory_store.add_skill(
            skill, job_id=job_id, review_round=review_round, comment=comment,
            memory=memory, master_skills=profile["master_skills"],
        )
        writes.append({"type": "skill", "value": skill, **result})

    for fact in facts.get("other_facts", []):
        result = memory_store.add_other_fact(
            fact, job_id=job_id, review_round=review_round, comment=comment, memory=memory,
        )
        writes.append({"type": "other_fact", "value": fact, **result})

    # Reload from disk so the profile every downstream tool reads is exactly
    # what was persisted -- no in-memory-only state.
    profile["memory"] = memory_store.load_memory()
    profile["memory_skills"] = memory_store.known_skills(profile["memory"])
    return writes


# ---------------------------------------------------------------------------
# Applying memory to a job's fit analysis (the same-run carry-over)
# ---------------------------------------------------------------------------

def refresh_fit_analysis_with_memory(job: dict, fit_analysis: dict, profile: dict) -> tuple:
    """Recomputes the deterministic skill buckets against the CURRENT
    profile (which now includes anything just written to memory) and folds
    the result back into the fit analysis.

    Returns (fit_analysis, newly_evidenced) where `newly_evidenced` lists
    required skills that just moved out of `genuine_gap` because of memory
    -- i.e. exactly what the Tailoring Tool is now allowed to add, and what
    the change log will cite memory for.

    This is a factual re-lookup (does this string now appear in the
    candidate's materials?), not a re-judgment of the LLM's fit narrative:
    the five dimension verdicts written by fit_analysis.py are left alone.
    """
    old_buckets = fit_analysis.get("skill_buckets") or {}
    old_gaps = [s.lower() for s in old_buckets.get("genuine_gap", [])]

    new_buckets = classify_required_skills(job, profile)
    newly_evidenced = [
        skill for skill in new_buckets["evidenced_elsewhere"]
        if skill.lower() in old_gaps
    ]

    fit_analysis["skill_buckets"] = new_buckets

    if newly_evidenced:
        core = fit_analysis.setdefault("core_skills", {})
        core["genuine_gap"] = [
            s for s in (core.get("genuine_gap") or [])
            if s.lower() not in [n.lower() for n in newly_evidenced]
        ]
        missing = core.setdefault("missing_evidenced", [])
        for skill in newly_evidenced:
            missing.append({"skill": skill, "evidence": memory_store.citation_for(skill, profile["memory"])})

    return fit_analysis, newly_evidenced


# ---------------------------------------------------------------------------
# Review of one job (presentation -> decision -> rework, capped)
# ---------------------------------------------------------------------------

def _changed_sections(before_log: list, after_log: list) -> list:
    """Which parts of the resume actually moved between two rounds -- this
    is what gets logged as 'actions taken' so a rework round can be shown
    to have done something concrete."""
    def index(log):
        out = {}
        for entry in log:
            out.setdefault(entry.get("section", "?"), []).append(entry.get("after", ""))
        return out

    before, after = index(before_log), index(after_log)
    changed = []
    for section in sorted(set(before) | set(after)):
        if before.get(section) != after.get(section):
            changed.append(section)
    return changed


def review_job(job: dict, fit_analysis: dict, profile: dict, tailor_result: dict,
               input_fn=input, max_rounds: int = MAX_REVISION_ROUNDS,
               carryover_actions: list = None) -> dict:
    """Runs the review conversation for ONE tailored resume.

    Returns {"job_id", "approved", "rounds": [...], "tailor_result",
    "fit_analysis", "memory_writes"}. Each round records the feedback
    received, the facts learned, and the actions taken -- Section 3.5's
    "log every round".

    carryover_actions: anything that happened to this resume BEFORE the
    reviewer saw it because of facts learned while reviewing an earlier
    resume in the same run. Logged as "round 0" so the carry-over is
    visible in this job's own review log.
    """
    rounds = []
    if carryover_actions:
        rounds.append({"round": 0, "decision": "memory carry-over (no reviewer input)",
                       "feedback": "", "facts_learned": [], "actions_taken": carryover_actions})
    all_memory_writes = []
    revisions_used = 0
    round_no = 1

    while True:
        print("\n" + format_change_log(job, tailor_result["change_log"]))
        print(f"\n  Tailored PDF: {os.path.relpath(tailor_result['pdf_path'], REPO_ROOT)}")

        decision, comment = prompt_decision(job, input_fn, round_no)

        if decision == "approve":
            rounds.append({"round": round_no, "decision": "approve", "feedback": "",
                           "facts_learned": [], "actions_taken": ["Reviewer approved the tailored resume."],
                           # The change log exactly as it was shown this round. Kept per round
                           # because tailoring.py overwrites outputs/<job_id>/change_log.json on
                           # every rework -- without this, the earlier rounds' edits would be
                           # unrecoverable and the review trail wouldn't be auditable.
                           "change_log_shown": tailor_result["change_log"]})
            print(f"  [{job['job_id']}] APPROVED.")
            return {"job_id": job["job_id"], "approved": True, "rounds": rounds,
                    "tailor_result": tailor_result, "fit_analysis": fit_analysis,
                    "memory_writes": all_memory_writes}

        # --- rejected: learn from the comment, then rework ---
        facts = extract_facts(comment, profile)
        memory_writes = write_facts_to_memory(facts, job["job_id"], round_no, comment, profile)
        all_memory_writes.extend(memory_writes)

        actions = []
        for write in memory_writes:
            if write["written"]:
                actions.append(
                    f"MEMORY WRITE: remembered {write['type']} '{write['value']}' "
                    f"(source: stated by candidate, review round {round_no}, job {job['job_id']})."
                )
                print(f"  [memory] wrote '{write['value']}' to memory/memory.json "
                      f"(stated by candidate, review round {round_no})")
            else:
                actions.append(f"MEMORY SKIPPED: '{write['value']}' -- {write['reason']}.")
        for rejected in facts.get("rejected", []):
            actions.append(
                f"MEMORY REJECTED: proposed {rejected['kind']} '{rejected['proposed']}' -- {rejected['reason']}."
            )

        fit_analysis, newly_evidenced = refresh_fit_analysis_with_memory(job, fit_analysis, profile)
        if newly_evidenced:
            actions.append(
                "Memory made these required skills addable for this job: " + ", ".join(newly_evidenced) + "."
            )

        if revisions_used >= max_rounds:
            # Cap reached. No further rework; the reviewer decides whether the
            # last version stands or the job is dropped. This is still the
            # same single pause, not a new gate.
            actions.append(f"Revision cap ({max_rounds} rounds) reached -- no further rework performed.")
            rounds.append({"round": round_no, "decision": "reject", "feedback": comment,
                           "facts_learned": [w["value"] for w in memory_writes if w["written"]],
                           "actions_taken": actions,
                           "change_log_shown": tailor_result["change_log"]})
            final = _prompt(
                input_fn,
                f"  [{job['job_id']}] Revision cap reached. Keep the last version "
                f"('approve') or drop this job ('skip')? ",
            ).lower()
            approved = final.startswith("a")
            rounds.append({"round": round_no, "decision": "approve" if approved else "skip",
                           "feedback": "", "facts_learned": [],
                           "actions_taken": ["Reviewer accepted the final version after the revision cap."
                                             if approved else
                                             "Reviewer dropped this job after the revision cap; no cover letter."]})
            print(f"  [{job['job_id']}] {'APPROVED (final version).' if approved else 'SKIPPED.'}")
            return {"job_id": job["job_id"], "approved": approved, "rounds": rounds,
                    "tailor_result": tailor_result, "fit_analysis": fit_analysis,
                    "memory_writes": all_memory_writes}

        revision_feedback = comment
        instructions = facts.get("tailoring_instructions") or []
        if instructions:
            revision_feedback = comment + " | Specifically: " + "; ".join(instructions)

        print(f"  [{job['job_id']}] Reworking with the reviewer's feedback "
              f"(revision {revisions_used + 1} of {max_rounds}) ...")
        previous_log = tailor_result["change_log"]
        tailor_result = tailor_resume(job, fit_analysis, profile, revision_feedback=revision_feedback)
        revisions_used += 1

        changed = _changed_sections(previous_log, tailor_result["change_log"])
        actions.append(
            "Re-ran the Tailoring Tool with the reviewer's comment as revision feedback; "
            + (f"sections that changed: {', '.join(changed)}." if changed
               else "the regenerated edits came back equivalent to the previous round.")
        )

        rounds.append({"round": round_no, "decision": "reject", "feedback": comment,
                       "facts_learned": [w["value"] for w in memory_writes if w["written"]],
                       "actions_taken": actions,
                       "change_log_shown": previous_log})
        round_no += 1


# ---------------------------------------------------------------------------
# Whole-session driver: review all 3, then cover letters for approved jobs
# ---------------------------------------------------------------------------

def _save_review_log(job: dict, review: dict) -> None:
    job_dir = os.path.join(OUTPUTS_DIR, job["job_id"])
    os.makedirs(job_dir, exist_ok=True)

    with open(os.path.join(job_dir, "review_log.json"), "w", encoding="utf-8") as f:
        json.dump({"job_id": job["job_id"], "title": job["title"], "company": job["company"],
                   "approved": review["approved"], "rounds": review["rounds"],
                   "memory_writes": review["memory_writes"]}, f, indent=2)

    lines = [f"# Human Review Log: {job['title']} @ {job['company']}  [{job['job_id']}]\n",
             f"**Final decision:** {'APPROVED' if review['approved'] else 'SKIPPED'}\n"]
    for entry in review["rounds"]:
        lines.append(f"## Round {entry['round']} -- {entry['decision'].upper()}")
        if entry.get("feedback"):
            lines.append(f"- **Feedback received:** {entry['feedback']}")
        if entry.get("facts_learned"):
            lines.append(f"- **Facts written to memory:** {', '.join(entry['facts_learned'])}")
        for action in entry.get("actions_taken", []):
            lines.append(f"- **Action:** {action}")
        lines.append("")
    with open(os.path.join(job_dir, "review_log.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _save_job_details(job: dict) -> None:
    job_dir = os.path.join(OUTPUTS_DIR, job["job_id"])
    os.makedirs(job_dir, exist_ok=True)
    with open(os.path.join(job_dir, "job_details.json"), "w", encoding="utf-8") as f:
        json.dump(job, f, indent=2)


def run_review_session(top3: list, profile: dict, input_fn=input,
                       max_rounds: int = MAX_REVISION_ROUNDS,
                       write_cover_letters: bool = True) -> dict:
    """The single human pause, for all Top-3 jobs, followed by the cover
    letters for every approved job.

    top3: [{"job": <job dict>, "fit_analysis": <dict>, "tailor_result": <dict>}, ...]
    input_fn: swappable for scripted/demo runs; defaults to real console input.
    """
    print("\n" + "#" * 78)
    print("# HUMAN REVIEW PAUSE -- the agent stops here exactly once.")
    print(f"# {len(top3)} tailored resumes to review. Approve each, or reject with comments")
    print(f"# (up to {max_rounds} revision rounds per resume). Skills you mention in a")
    print("# comment are written to memory and reused for the remaining resumes.")
    print("#" * 78)

    reviews = []
    for position, item in enumerate(top3, 1):
        job, fit_analysis, tailor_result = item["job"], item["fit_analysis"], item["tailor_result"]
        print(f"\n\n>>> Resume {position} of {len(top3)}: [{job['job_id']}] "
              f"{job['title']} @ {job['company']}")

        # Same-run carry-over: anything learned while reviewing an earlier
        # resume is applied here BEFORE this one is shown, without the
        # reviewer having to repeat themselves.
        fit_analysis, newly_evidenced = refresh_fit_analysis_with_memory(job, fit_analysis, profile)
        carryover_actions = []
        if newly_evidenced:
            print(f"  [memory] {', '.join(newly_evidenced)} now counts as evidenced for this job "
                  f"(learned earlier in this run) -- re-tailoring before review.")
            tailor_result = tailor_resume(
                job, fit_analysis, profile,
                revision_feedback=("Facts learned from the candidate earlier in this review session: "
                                   + ", ".join(newly_evidenced)),
            )
            carryover_actions.append(
                "Memory learned earlier in this run made these required skills evidenced for this "
                f"job: {', '.join(newly_evidenced)}. The resume was re-tailored with them BEFORE "
                "the reviewer saw it -- the candidate did not have to repeat themselves "
                f"({memory_store.citation_for(newly_evidenced[0], profile['memory'])})."
            )

        review = review_job(job, fit_analysis, profile, tailor_result,
                            input_fn=input_fn, max_rounds=max_rounds,
                            carryover_actions=carryover_actions)
        _save_review_log(job, review)
        _save_job_details(job)
        reviews.append({"job": job, **review})

    approved = [r for r in reviews if r["approved"]]
    print("\n" + "#" * 78)
    print(f"# Review complete: {len(approved)} of {len(reviews)} resumes approved.")
    memory = memory_store.load_memory()
    print(f"# Memory now holds {len(memory['skills_learned'])} learned skill(s): "
          f"{', '.join(memory_store.known_skills(memory)) or '(none)'}")
    print("#" * 78)

    letters = []
    if write_cover_letters:
        for review in approved:
            job = review["job"]
            print(f"\nGenerating cover letter for [{job['job_id']}] {job['title']} @ {job['company']} ...")
            letter = cover_letter_tool.generate_cover_letter(job, review["fit_analysis"], profile)
            for line in letter["evidence_log"]:
                print(f"    {line}")
            print(f"  -> {os.path.relpath(letter['pdf_path'], REPO_ROOT)}")
            letters.append(letter)

    session = {
        "reviewed": [{"job_id": r["job_id"], "approved": r["approved"],
                      "rounds": len(r["rounds"]),
                      "memory_writes": [w["value"] for w in r["memory_writes"] if w["written"]]}
                     for r in reviews],
        "approved_job_ids": [r["job_id"] for r in approved],
        "cover_letters": [{"job_id": l["job_id"],
                           "pdf": os.path.relpath(l["pdf_path"], REPO_ROOT)} for l in letters],
        "memory_after_session": memory_store.load_memory(),
    }
    with open(os.path.join(OUTPUTS_DIR, "review_session.json"), "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2)
    return session


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def scripted_input(responses: list):
    """Test/demo aid: replays a canned list of reviewer answers instead of
    reading the console, so a full review session can be reproduced
    exactly (and re-run in CI or during a demo recording). The real pause
    still uses `input` by default."""
    queue = list(responses)

    def _input(prompt_text: str = "") -> str:
        answer = queue.pop(0) if queue else "approve"
        print(f"{prompt_text}{answer}")
        return answer

    return _input


def _load_top3(profile: dict) -> list:
    """Rebuilds the review queue from what the earlier workstreams left on
    disk: the ranked Top 3, each job's fit analysis, and each job's
    already-tailored resume + change log."""
    with open(os.path.join(OUTPUTS_DIR, "ranked_jobs.json"), encoding="utf-8") as f:
        top3_job_ids = json.load(f)["top3_job_ids"]

    all_jobs = {j["job_id"]: j for j in load_jobs(os.path.join(REPO_ROOT, "data", "jobs.csv"))}
    queue = []
    for job_id in top3_job_ids:
        job_dir = os.path.join(OUTPUTS_DIR, job_id)
        with open(os.path.join(job_dir, "fit_analysis.json"), encoding="utf-8") as f:
            fit_analysis = json.load(f)
        with open(os.path.join(job_dir, "change_log.json"), encoding="utf-8") as f:
            change_log = json.load(f)
        queue.append({
            "job": all_jobs[job_id],
            "fit_analysis": fit_analysis,
            "tailor_result": {
                "job_id": job_id,
                "tex_path": os.path.join(job_dir, "resume_tailored.tex"),
                "pdf_path": os.path.join(job_dir, "resume_after.pdf"),
                "before_pdf_path": os.path.join(job_dir, "resume_before.pdf"),
                "change_log": change_log,
            },
        })
    return queue


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Human review pause + memory + cover letters.")
    parser.add_argument("--reset-memory", action="store_true",
                        help="wipe memory/memory.json before starting (clean end-to-end run)")
    parser.add_argument("--script", metavar="FILE",
                        help="JSON file with a list of canned reviewer answers (replays a session "
                             "instead of prompting -- for tests and demo recordings)")
    parser.add_argument("--no-cover-letters", action="store_true",
                        help="stop after the review pause (skip cover letter generation)")
    args = parser.parse_args()

    if args.reset_memory:
        memory_store.reset()
        print("memory/memory.json reset to empty.")

    input_fn = input
    if args.script:
        with open(args.script, encoding="utf-8") as f:
            input_fn = scripted_input(json.load(f))

    profile = load_full_profile()
    run_review_session(_load_top3(profile), profile, input_fn=input_fn,
                       write_cover_letters=not args.no_cover_letters)
