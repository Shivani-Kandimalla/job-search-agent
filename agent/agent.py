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
            write_cover_letters=True,
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


def run_pipeline(
    *,
    reset_memory: bool = False,
    script_path: Path | None = None,
) -> dict:
    """Run the complete job-search workflow under one public trace."""
    if reset_memory:
        memory_store.reset()
        print("memory/memory.json reset to empty.")

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
        },
        metadata={
            "workstream": "Person 5 - orchestration and tracing",
            "trace_platform": "Langfuse",
        },
    ) as root_span:
        print("Running filtering and deterministic scoring...")
        state = run_filtering_and_scoring()

        print(
            "Top 3:",
            ", ".join(
                result["job_id"]
                for result in state["top3_scores"]
            ),
        )

        top3_items = run_top3_generation(state)

        print("\nStarting the single human-review pause...")
        review_session = run_human_review(
            top3_items,
            state["profile"],
            script_path=script_path,
        )

        result = {
            "status": "completed",
            "filtered_job_count": len(state["kept"]),
            "rejected_job_count": len(state["rejected"]),
            "top3_job_ids": [
                result["job_id"]
                for result in state["top3_scores"]
            ],
            "approved_job_ids": review_session[
                "approved_job_ids"
            ],
            "cover_letters": review_session[
                "cover_letters"
            ],
            "memory_after_session": review_session[
                "memory_after_session"
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
