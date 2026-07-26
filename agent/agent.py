from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "agent" / "tools"
OUTPUTS_DIR = REPO_ROOT / "outputs"

# The teammates' tool files use imports such as "from profile import ...".
# Adding agent/tools here lets the orchestrator import them without editing
# any teammate-owned source file.
for directory in (REPO_ROOT, TOOLS_DIR):
    directory_text = str(directory)
    if directory_text not in sys.path:
        sys.path.insert(0, directory_text)

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from person5_tracing import (
    flush_traces,
    publish_current_trace,
    traced_step,
)

import memory_store
from filtering import filter_jobs, load_jobs, load_preferences
from fit_analysis import analyze_fit, format_report
from human_review import run_review_session, scripted_input
from profile import load_full_profile
from scoring import score_and_rank
from tailoring import tailor_resume


def save_json(path: Path, data: object) -> None:
    """Save structured pipeline output in readable JSON format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def safe_format_change_log(job: dict, change_log: list) -> str:
    """Format all change-log entries, including one-page trimming entries."""
    lines = [
        f"# Change Log: {job['title']} @ {job['company']}  [{job['job_id']}]\n"
    ]

    for entry in change_log:
        lines.append(f"## {entry.get('section', 'unknown')}")

        if "before" in entry:
            lines.append(f"- **Before:** {entry['before']}")

        if "after" in entry:
            lines.append(f"- **After:** {entry['after']}")

        if entry.get("action"):
            lines.append(f"- **Action:** {entry['action']}")

        lines.append(
            f"- **Citation:** {entry.get('citation', 'One-Page Rule formatting adjustment')}"
        )
        lines.append(
            f"- **Reason:** {entry.get('reason', entry.get('action', 'Adjusted to keep the resume to one page.'))}\n"
        )

    return "\n".join(lines)

import tailoring as tailoring_tool

# Runtime compatibility fix:
# the tailoring tool's One-Page Rule creates some log entries without
# citation/reason fields. Replace only its formatter while this orchestrator runs.
tailoring_tool._format_change_log = safe_format_change_log

import os

import cover_letter as cover_letter_tool
import fit_analysis as fit_analysis_tool
import human_review as human_review_tool
import llm_client as llm_client_tool


def install_runtime_tracing() -> None:
    """Trace existing tools without modifying teammate-owned files."""
    if getattr(llm_client_tool, "_person5_tracing_installed", False):
        return

    original_chat = llm_client_tool.chat
    original_memory_write = human_review_tool.write_facts_to_memory

    def traced_chat(
        *,
        messages: list,
        temperature: float = 0.2,
        response_format: dict | None = None,
    ) -> str:
        model = os.getenv("OLLAMA_MODEL", "llama3.2")

        with traced_step(
            "llm-chat",
            input_data={
                "messages": messages,
                "temperature": temperature,
                "response_format": response_format,
            },
            metadata={
                "provider": "Ollama",
                "model": model,
            },
            observation_type="generation",
        ) as generation:
            response = original_chat(
                messages=messages,
                temperature=temperature,
                response_format=response_format,
            )
            generation.update(output=response)
            return response

    def traced_memory_write(
        facts: dict,
        job_id: str,
        review_round: int,
        comment: str,
        profile: dict,
    ) -> list:
        with traced_step(
            "memory-write",
            input_data={
                "job_id": job_id,
                "review_round": review_round,
                "facts": facts,
                "review_comment": comment,
            },
            metadata={"file": "memory/memory.json"},
        ) as span:
            writes = original_memory_write(
                facts,
                job_id,
                review_round,
                comment,
                profile,
            )
            span.update(
                output={
                    "writes": writes,
                    "memory_skills_after_write": profile.get(
                        "memory_skills", []
                    ),
                }
            )
            return writes

    # Each teammate module imported chat directly, so replace its local reference.
    fit_analysis_tool.chat = traced_chat
    tailoring_tool.chat = traced_chat
    human_review_tool.chat = traced_chat
    cover_letter_tool.chat = traced_chat

    # Make memory persistence visible as its own trace span.
    human_review_tool.write_facts_to_memory = traced_memory_write

    llm_client_tool._person5_tracing_installed = True


install_runtime_tracing()


def run_filtering_and_scoring() -> dict:
    """Run deterministic filtering and scoring, then select the Top 3."""
    jobs_path = REPO_ROOT / "data" / "jobs.csv"
    preferences_path = REPO_ROOT / "data" / "persona_preferences.json"

    jobs = load_jobs(str(jobs_path))
    preferences = load_preferences(str(preferences_path))
    profile = load_full_profile()

    with traced_step(
        "filter-jobs",
        input_data={
            "job_count": len(jobs),
            "preferences": preferences,
        },
    ) as span:
        kept, rejected = filter_jobs(jobs, preferences)
        span.update(
            output={
                "kept_job_ids": [job["job_id"] for job in kept],
                "rejected": [
                    {
                        "job_id": job["job_id"],
                        "reason": job["rejection_reason"],
                    }
                    for job in rejected
                ],
            }
        )

    with traced_step(
        "score-and-rank-jobs",
        input_data={
            "kept_job_ids": [job["job_id"] for job in kept],
            "scoring_method": (
                "0.5 skill_match + 0.3 experience_alignment "
                "+ 0.2 domain_alignment"
            ),
        },
    ) as span:
        ranked = score_and_rank(kept, profile)
        top3_scores = ranked[:3]

        span.update(
            output={
                "ranked_jobs": ranked,
                "top3_job_ids": [
                    result["job_id"] for result in top3_scores
                ],
            }
        )

    save_json(
        OUTPUTS_DIR / "ranked_jobs.json",
        {
            "ranked": ranked,
            "top3_job_ids": [
                result["job_id"] for result in top3_scores
            ],
        },
    )

    jobs_by_id = {
        job["job_id"]: job
        for job in jobs
    }

    return {
        "profile": profile,
        "jobs_by_id": jobs_by_id,
        "kept": kept,
        "rejected": rejected,
        "ranked": ranked,
        "top3_scores": top3_scores,
    }


def run_top3_generation(state: dict) -> list:
    """Generate fit analyses and tailored resumes for the Top 3 jobs."""
    profile = state["profile"]
    jobs_by_id = state["jobs_by_id"]
    top3_items = []

    for position, score_breakdown in enumerate(
        state["top3_scores"],
        start=1,
    ):
        job_id = score_breakdown["job_id"]
        job = jobs_by_id[job_id]
        job_dir = OUTPUTS_DIR / job_id

        print(
            f"[{position}/3] Analyzing "
            f"{job['title']} @ {job['company']}..."
        )

        with traced_step(
            f"fit-analysis-{job_id}",
            input_data={
                "job": job,
                "score_breakdown": score_breakdown,
            },
            metadata={
                "job_id": job_id,
                "tool": "fit_analysis.py",
            },
        ) as span:
            fit_analysis = analyze_fit(
                job,
                profile,
                score_breakdown,
            )
            span.update(output=fit_analysis)

        save_json(
            job_dir / "fit_analysis.json",
            fit_analysis,
        )
        (job_dir / "fit_analysis.txt").write_text(
            format_report(fit_analysis),
            encoding="utf-8",
        )

        print(f"[{position}/3] Tailoring resume for {job_id}...")

        with traced_step(
            f"tailor-resume-{job_id}",
            input_data={
                "job_id": job_id,
                "fit_analysis": fit_analysis,
            },
            metadata={
                "job_id": job_id,
                "tool": "tailoring.py",
                "one_page_rule": True,
            },
        ) as span:
            tailor_result = tailor_resume(
                job,
                fit_analysis,
                profile,
            )

            span.update(
                output={
                    "job_id": job_id,
                    "pdf_path": str(
                        Path(tailor_result["pdf_path"]).relative_to(
                            REPO_ROOT
                        )
                    ),
                    "change_log": tailor_result["change_log"],
                }
            )

        top3_items.append(
            {
                "job": job,
                "fit_analysis": fit_analysis,
                "tailor_result": tailor_result,
            }
        )

    return top3_items


def install_review_tool_spans() -> None:
    """Trace tailoring revisions and cover-letter generation."""
    if getattr(
        human_review_tool,
        "_person5_tool_spans_installed",
        False,
    ):
        return

    original_revision_tailor = human_review_tool.tailor_resume
    original_cover_letter = cover_letter_tool.generate_cover_letter

    def traced_revision_tailor(
        job: dict,
        fit_analysis: dict,
        profile: dict,
        revision_feedback: str | None = None,
    ) -> dict:
        job_id = job["job_id"]

        with traced_step(
            f"tailor-resume-review-{job_id}",
            input_data={
                "job_id": job_id,
                "revision_feedback": revision_feedback,
                "fit_analysis": fit_analysis,
            },
            metadata={
                "tool": "tailoring.py",
                "review_revision": bool(revision_feedback),
            },
        ) as span:
            result = original_revision_tailor(
                job,
                fit_analysis,
                profile,
                revision_feedback=revision_feedback,
            )

            span.update(
                output={
                    "job_id": job_id,
                    "pdf_path": str(
                        Path(result["pdf_path"]).relative_to(REPO_ROOT)
                    ),
                    "change_log": result["change_log"],
                }
            )
            return result

    def traced_cover_letter(
        job: dict,
        fit_analysis: dict,
        profile: dict,
    ) -> dict:
        job_id = job["job_id"]

        with traced_step(
            f"cover-letter-{job_id}",
            input_data={
                "job": job,
                "fit_analysis": fit_analysis,
            },
            metadata={
                "tool": "cover_letter.py",
                "job_id": job_id,
            },
        ) as span:
            result = original_cover_letter(
                job,
                fit_analysis,
                profile,
            )

            span.update(
                output={
                    "job_id": job_id,
                    "pdf_path": str(
                        Path(result["pdf_path"]).relative_to(REPO_ROOT)
                    ),
                    "evidence_log": result.get("evidence_log", []),
                }
            )
            return result

    human_review_tool.tailor_resume = traced_revision_tailor
    cover_letter_tool.generate_cover_letter = traced_cover_letter
    human_review_tool._person5_tool_spans_installed = True


install_review_tool_spans()


def run_human_review(
    top3_items: list,
    profile: dict,
    script_path: Path | None = None,
) -> dict:
    """Pause once for review, then generate approved cover letters."""
    input_fn = input
    review_mode = "interactive"

    if script_path is not None:
        responses = json.loads(
            script_path.read_text(encoding="utf-8")
        )
        input_fn = scripted_input(responses)
        review_mode = "scripted"

    with traced_step(
        "human-review-pause",
        input_data={
            "review_mode": review_mode,
            "top3_job_ids": [
                item["job"]["job_id"]
                for item in top3_items
            ],
            "maximum_revision_rounds": 2,
        },
        metadata={
            "single_human_pause": True,
            "memory_file": "memory/memory.json",
        },
    ) as span:
        session = run_review_session(
            top3_items,
            profile,
            input_fn=input_fn,
            max_rounds=2,
            write_cover_letters=False,
        )

        span.update(output=session)
        return session


def resolve_script_path(value: str | None) -> Path | None:
    """Resolve an optional review-response script path."""
    if not value:
        return None

    path = Path(value)

    if not path.is_absolute():
        path = REPO_ROOT / path

    path = path.resolve()

    if not path.is_file():
        raise FileNotFoundError(
            f"Review script was not found: {path}"
        )

    return path



AGENT_SYSTEM_PROMPT = """
You are the single orchestration agent for a Job Search Agent.

Choose exactly one next tool based on the current workflow state.

Select only a tool listed under currently_valid_tools.
Never select a tool that already appears in completed_tools.
When currently_valid_tools contains one tool, select that tool.
After generate_cover_letters completes, select finish.

Return JSON only:
{
  "tool": "one tool name",
  "reason": "one concise sentence explaining why this tool is next"
}

Rules:
- The LLM chooses the next tool; do not describe multiple future actions.
- At startup, the source jobs dataset exists even when filtered_job_count is 0 because filtering has not run yet.`r`n- The first tool must be filter_jobs.`r`n- Filtering must occur before scoring.
- Scoring is deterministic code. Never invent or estimate job scores.
- Scoring must occur before fit analysis.
- Fit analysis must occur before resume tailoring.
- After tailoring, the program enforces the one required human-review pause.
- The human-review pause is structural and is not a selectable tool.
- Cover letters can run only after human review is complete.
- Finish only after cover letters are generated.
- Never request another human pause.
"""

AGENT_TOOL_SCHEMAS = [
    {
        "name": "filter_jobs",
        "description": (
            "Apply deterministic candidate preferences to the jobs dataset "
            "and log a reason for every rejected job."
        ),
        "arguments": {},
    },
    {
        "name": "score_jobs",
        "description": (
            "Use deterministic Python scoring on the filtered jobs, rank "
            "them, and select the Top 3. The LLM never creates scores."
        ),
        "arguments": {},
    },
    {
        "name": "fit_analysis",
        "description": (
            "Run evidence-grounded LLM fit analysis for each Top-3 job, "
            "including skill gaps and project-swap recommendations."
        ),
        "arguments": {},
    },
    {
        "name": "tailor_resumes",
        "description": (
            "Create evidence-backed one-page tailored resumes and change "
            "logs for all Top-3 jobs."
        ),
        "arguments": {},
    },
    {
        "name": "generate_cover_letters",
        "description": (
            "Generate one-page cover-letter PDFs for resumes approved "
            "during the structural human-review pause."
        ),
        "arguments": {},
    },
    {
        "name": "finish",
        "description": (
            "Finish the workflow after all required tools and the human "
            "review have completed."
        ),
        "arguments": {},
    },
]

AGENT_TOOL_PREREQUISITES = {
    "filter_jobs": [],
    "score_jobs": ["filter_jobs"],
    "fit_analysis": ["score_jobs"],
    "tailor_resumes": ["fit_analysis"],
    "generate_cover_letters": ["tailor_resumes"],
}


def planner_state_summary(state: dict) -> dict:
    """Return a compact state representation for the orchestration LLM."""
    return {
        "completed_tools": state.get("completed_tools", []),
        "filtered_job_count": len(state.get("kept", [])),
        "rejected_job_count": len(state.get("rejected", [])),
        "top3_job_ids": [
            item.get("job_id")
            for item in state.get("top3_scores", [])
        ],
        "human_review_complete": state.get(
            "human_review_complete",
            False,
        ),
        "approved_job_ids": state.get(
            "approved_job_ids",
            [],
        ),
        "cover_letter_count": len(
            state.get("cover_letters", [])
        ),
    }


def parse_agent_decision(response: str) -> dict:
    """Parse and validate the orchestration LLM's JSON decision."""
    cleaned = response.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()

        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    decision = json.loads(cleaned)

    if not isinstance(decision, dict):
        raise ValueError("The agent decision must be a JSON object.")

    tool = decision.get("tool")
    reason = decision.get("reason")

    if not isinstance(tool, str) or not tool.strip():
        raise ValueError("The agent decision is missing 'tool'.")

    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("The agent decision is missing 'reason'.")

    return {
        "tool": tool.strip(),
        "reason": reason.strip(),
    }


def choose_agent_action(
    state: dict,
    *,
    step_number: int,
    correction: str | None = None,
) -> dict:
    """Ask the single orchestration LLM to choose the next tool."""
    valid_tool_names = [
        schema["name"]
        for schema in AGENT_TOOL_SCHEMAS
        if validate_agent_action(
            state,
            schema["name"],
        ) is None
    ]

    currently_valid_tools = [
        schema
        for schema in AGENT_TOOL_SCHEMAS
        if schema["name"] in valid_tool_names
    ]

    valid_tool_names_text = ", ".join(valid_tool_names)

    selection_constraint = (
        "For this reasoning step, the only legal tool "
        f"name or names are: {valid_tool_names_text}. "
        "Your JSON tool value must exactly match one "
        "of those names."
    )

    prompt_data = {
        "workflow_state": planner_state_summary(state),
        "currently_valid_tools": currently_valid_tools,
        "selection_constraint": selection_constraint,
        "previous_decision_error": correction,
    }

    messages = [
        {
            "role": "system",
            "content": (
                AGENT_SYSTEM_PROMPT
                + "\n\n"
                + selection_constraint
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                prompt_data,
                indent=2,
            ),
        },
    ]

    with traced_step(
        f"agent-reasoning-step-{step_number}",
        input_data={
            "system_prompt": AGENT_SYSTEM_PROMPT,
            "messages": messages,
            "registered_tools": AGENT_TOOL_SCHEMAS,
            "currently_valid_tools": currently_valid_tools,
            "workflow_state": planner_state_summary(state),
        },
        metadata={
            "agent_type": "single-llm-reasoning-loop",
            "model": os.getenv("OLLAMA_MODEL", "llama3.2"),
            "step_number": step_number,
        },
        observation_type="generation",
    ) as generation:
        response = llm_client_tool.chat(
            messages=messages,
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        decision = parse_agent_decision(response)

        generation.update(
            output={
                "raw_response": response,
                "selected_tool": decision["tool"],
                "selection_reason": decision["reason"],
            }
        )

        return decision


def validate_agent_action(state: dict, tool_name: str) -> str | None:
    """Return an error message when the selected action is not currently valid."""
    completed = state.get("completed_tools", [])

    valid_names = {
        tool["name"]
        for tool in AGENT_TOOL_SCHEMAS
    }

    if tool_name not in valid_names:
        return f"Unknown tool '{tool_name}'."

    if tool_name == "finish":
        if "generate_cover_letters" not in completed:
            return (
                "The workflow cannot finish before "
                "generate_cover_letters completes."
            )
        return None

    if tool_name in completed:
        return f"Tool '{tool_name}' has already completed."

    missing = [
        requirement
        for requirement in AGENT_TOOL_PREREQUISITES[tool_name]
        if requirement not in completed
    ]

    if missing:
        return (
            f"Tool '{tool_name}' cannot run yet. "
            f"Missing prerequisites: {', '.join(missing)}."
        )

    if (
        tool_name == "generate_cover_letters"
        and not state.get("human_review_complete", False)
    ):
        return (
            "Cover letters cannot run until the structural "
            "human-review pause is complete."
        )

    return None



def execute_filter_jobs(state: dict) -> dict:
    """Execute deterministic job filtering."""
    jobs_path = REPO_ROOT / "data" / "jobs.csv"
    preferences_path = (
        REPO_ROOT / "data" / "persona_preferences.json"
    )

    jobs = load_jobs(str(jobs_path))
    preferences = load_preferences(str(preferences_path))
    profile = load_full_profile()

    with traced_step(
        "tool-filter-jobs",
        input_data={
            "job_count": len(jobs),
            "preferences": preferences,
        },
        metadata={"tool": "filtering.py"},
    ) as span:
        kept, rejected = filter_jobs(jobs, preferences)

        output = {
            "kept_job_ids": [
                job["job_id"]
                for job in kept
            ],
            "rejected_jobs": [
                {
                    "job_id": job["job_id"],
                    "reason": job["rejection_reason"],
                }
                for job in rejected
            ],
        }
        span.update(output=output)

    state.update(
        {
            "jobs": jobs,
            "preferences": preferences,
            "profile": profile,
            "kept": kept,
            "rejected": rejected,
        }
    )
    state["completed_tools"].append("filter_jobs")

    return output


def execute_score_jobs(state: dict) -> dict:
    """Execute deterministic scoring and Top-3 selection."""
    with traced_step(
        "tool-score-jobs",
        input_data={
            "kept_job_ids": [
                job["job_id"]
                for job in state["kept"]
            ],
            "formula": (
                "0.5 skill_match + "
                "0.3 experience_alignment + "
                "0.2 domain_alignment"
            ),
        },
        metadata={
            "tool": "scoring.py",
            "deterministic": True,
            "llm_scoring": False,
        },
    ) as span:
        ranked = score_and_rank(
            state["kept"],
            state["profile"],
        )
        top3_scores = ranked[:3]

        output = {
            "ranked_jobs": ranked,
            "top3_job_ids": [
                item["job_id"]
                for item in top3_scores
            ],
        }
        span.update(output=output)

    save_json(
        OUTPUTS_DIR / "ranked_jobs.json",
        {
            "ranked": ranked,
            "top3_job_ids": output["top3_job_ids"],
        },
    )

    state.update(
        {
            "ranked": ranked,
            "top3_scores": top3_scores,
            "jobs_by_id": {
                job["job_id"]: job
                for job in state["jobs"]
            },
        }
    )
    state["completed_tools"].append("score_jobs")

    return output


def execute_fit_analysis(state: dict) -> dict:
    """Run fit analysis for each deterministically selected Top-3 job."""
    top3_items = []

    for position, score_breakdown in enumerate(
        state["top3_scores"],
        start=1,
    ):
        job_id = score_breakdown["job_id"]
        job = state["jobs_by_id"][job_id]
        job_dir = OUTPUTS_DIR / job_id

        print(
            f"[{position}/3] Running fit analysis "
            f"for {job_id}..."
        )

        with traced_step(
            f"tool-fit-analysis-{job_id}",
            input_data={
                "job": job,
                "score_breakdown": score_breakdown,
            },
            metadata={
                "tool": "fit_analysis.py",
                "job_id": job_id,
            },
        ) as span:
            fit_analysis = analyze_fit(
                job,
                state["profile"],
                score_breakdown,
            )
            span.update(output=fit_analysis)

        save_json(
            job_dir / "fit_analysis.json",
            fit_analysis,
        )
        (job_dir / "fit_analysis.txt").write_text(
            format_report(fit_analysis),
            encoding="utf-8",
        )

        top3_items.append(
            {
                "job": job,
                "fit_analysis": fit_analysis,
            }
        )

    state["top3_items"] = top3_items
    state["completed_tools"].append("fit_analysis")

    return {
        "analyzed_job_ids": [
            item["job"]["job_id"]
            for item in top3_items
        ]
    }


def execute_tailor_resumes(state: dict) -> dict:
    """Tailor one-page resumes for all Top-3 jobs."""
    tailored = []

    for position, item in enumerate(
        state["top3_items"],
        start=1,
    ):
        job = item["job"]
        job_id = job["job_id"]

        print(
            f"[{position}/3] Tailoring resume "
            f"for {job_id}..."
        )

        with traced_step(
            f"tool-tailor-resume-{job_id}",
            input_data={
                "job_id": job_id,
                "fit_analysis": item["fit_analysis"],
            },
            metadata={
                "tool": "tailoring.py",
                "job_id": job_id,
                "one_page_rule": True,
            },
        ) as span:
            tailor_result = tailor_resume(
                job,
                item["fit_analysis"],
                state["profile"],
            )

            output = {
                "job_id": job_id,
                "pdf_path": str(
                    Path(
                        tailor_result["pdf_path"]
                    ).relative_to(REPO_ROOT)
                ),
                "change_log": tailor_result[
                    "change_log"
                ],
            }
            span.update(output=output)

        item["tailor_result"] = tailor_result
        tailored.append(output)

    state["completed_tools"].append("tailor_resumes")

    return {"tailored_resumes": tailored}


def execute_generate_cover_letters(state: dict) -> dict:
    """Generate cover letters only for approved jobs."""
    approved = set(state["approved_job_ids"])
    letters = []

    with traced_step(
        "tool-generate-cover-letters",
        input_data={
            "approved_job_ids": sorted(approved),
        },
        metadata={"tool": "cover_letter.py"},
    ) as span:
        for item in state["top3_items"]:
            job = item["job"]
            job_id = job["job_id"]

            if job_id not in approved:
                continue

            print(
                f"Generating cover letter for "
                f"{job_id}..."
            )

            letter = (
                cover_letter_tool.generate_cover_letter(
                    job,
                    item["fit_analysis"],
                    state["profile"],
                )
            )

            letters.append(
                {
                    "job_id": job_id,
                    "pdf": str(
                        Path(
                            letter["pdf_path"]
                        ).relative_to(REPO_ROOT)
                    ),
                }
            )

        span.update(output={"cover_letters": letters})

    state["cover_letters"] = letters
    state["completed_tools"].append(
        "generate_cover_letters"
    )

    return {"cover_letters": letters}


def run_pipeline(
    *,
    reset_memory: bool = False,
    script_path: Path | None = None,
) -> dict:
    """Run the workflow through one LLM-controlled reasoning loop."""
    if reset_memory:
        memory_store.reset()
        print("memory/memory.json reset to empty.")

    state = {
        "completed_tools": [],
        "human_review_complete": False,
        "approved_job_ids": [],
        "cover_letters": [],
        "agent_decisions": [],
    }

    tool_handlers = {
        "filter_jobs": execute_filter_jobs,
        "score_jobs": execute_score_jobs,
        "fit_analysis": execute_fit_analysis,
        "tailor_resumes": execute_tailor_resumes,
        "generate_cover_letters": execute_generate_cover_letters,
    }

    with traced_step(
        "job-search-agent-end-to-end",
        input_data={
            "reset_memory": reset_memory,
            "review_mode": (
                "scripted" if script_path else "interactive"
            ),
            "review_script": (
                str(script_path.relative_to(REPO_ROOT))
                if script_path
                else None
            ),
            "architecture": "single LLM reasoning loop",
            "available_tools": AGENT_TOOL_SCHEMAS,
        },
        metadata={
            "workstream": "Person 5 - orchestration and tracing",
            "trace_platform": "Langfuse",
            "single_agent": True,
            "llm_selects_tools": True,
            "deterministic_scoring": True,
            "single_human_pause": True,
        },
    ) as root_span:
        correction = None
        finished = False

        for step_number in range(1, 16):
            decision = choose_agent_action(
                state,
                step_number=step_number,
                correction=correction,
            )

            tool_name = decision["tool"]
            reason = decision["reason"]
            validation_error = validate_agent_action(
                state,
                tool_name,
            )

            decision_record = {
                "step": step_number,
                "selected_tool": tool_name,
                "reason": reason,
                "valid": validation_error is None,
            }

            if validation_error:
                decision_record["validation_error"] = (
                    validation_error
                )
                state["agent_decisions"].append(
                    decision_record
                )

                print(
                    f"[Agent step {step_number}] "
                    f"Rejected invalid choice: {tool_name}"
                )
                print("Reason:", validation_error)

                correction = validation_error
                continue

            state["agent_decisions"].append(decision_record)
            correction = None

            print(
                f"\n[Agent step {step_number}] "
                f"Selected tool: {tool_name}"
            )
            print("Reason:", reason)

            if tool_name == "finish":
                finished = True
                break

            with traced_step(
                f"agent-tool-call-{tool_name}",
                input_data={
                    "selected_tool": tool_name,
                    "selection_reason": reason,
                    "workflow_state_before": (
                        planner_state_summary(state)
                    ),
                },
                metadata={
                    "selected_by_llm": True,
                    "agent_step": step_number,
                },
            ) as tool_span:
                tool_output = tool_handlers[tool_name](
                    state
                )

                tool_span.update(
                    output={
                        "tool_result": tool_output,
                        "workflow_state_after": (
                            planner_state_summary(state)
                        ),
                    }
                )

            if tool_name == "tailor_resumes":
                print(
                    "\nStarting the one structural "
                    "human-review pause..."
                )

                review_session = run_human_review(
                    state["top3_items"],
                    state["profile"],
                    script_path=script_path,
                )

                state["review_session"] = review_session
                state["human_review_complete"] = True
                state["approved_job_ids"] = review_session[
                    "approved_job_ids"
                ]
                state["memory_after_session"] = (
                    review_session["memory_after_session"]
                )

        if not finished:
            raise RuntimeError(
                "The orchestration agent did not finish "
                "within 15 reasoning steps."
            )

        result = {
            "status": "completed",
            "architecture": "single LLM reasoning loop",
            "filtered_job_count": len(state["kept"]),
            "rejected_job_count": len(state["rejected"]),
            "top3_job_ids": [
                item["job_id"]
                for item in state["top3_scores"]
            ],
            "approved_job_ids": state[
                "approved_job_ids"
            ],
            "cover_letters": state["cover_letters"],
            "memory_after_session": state.get(
                "memory_after_session",
                memory_store.load_memory(),
            ),
            "completed_tools": state[
                "completed_tools"
            ],
            "agent_decisions": state[
                "agent_decisions"
            ],
        }

        trace_id, trace_url = publish_current_trace()
        result["trace_id"] = trace_id
        result["trace_url"] = trace_url

        root_span.update(output=result)

    flush_traces()

    save_json(
        OUTPUTS_DIR / "person5_run_summary.json",
        result,
    )

    print("\nPipeline completed.")
    print("Public trace:", result["trace_url"])
    print(
        "Run summary:",
        "outputs/person5_run_summary.json",
    )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the complete Job Search Agent with "
            "Langfuse tracing."
        )
    )
    parser.add_argument(
        "--reset-memory",
        action="store_true",
        help=(
            "Reset memory/memory.json before the run."
        ),
    )
    parser.add_argument(
        "--script",
        metavar="FILE",
        help=(
            "Use a JSON file of scripted human-review "
            "responses instead of typing them manually."
        ),
    )
    args = parser.parse_args()

    script_path = resolve_script_path(args.script)

    run_pipeline(
        reset_memory=args.reset_memory,
        script_path=script_path,
    )


if __name__ == "__main__":
    main()
