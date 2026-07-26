from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv
from langfuse import get_client


REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

langfuse = get_client()


@contextmanager
def traced_step(
    name: str,
    *,
    input_data: Any = None,
    metadata: dict[str, Any] | None = None,
    observation_type: str = "span",
) -> Iterator[Any]:
    """Create one Langfuse observation around a pipeline step."""
    with langfuse.start_as_current_observation(
        name=name,
        as_type=observation_type,
        input=input_data,
        metadata=metadata,
    ) as observation:
        try:
            yield observation
        except Exception as error:
            observation.update(
                level="ERROR",
                status_message=str(error),
                output={
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
            )
            raise


def publish_current_trace() -> tuple[str, str]:
    """Make the active trace public and return its ID and URL."""
    trace_id = langfuse.get_current_trace_id()

    if not trace_id:
        raise RuntimeError("No active Langfuse trace was found.")

    langfuse.set_current_trace_as_public()
    trace_url = langfuse.get_trace_url(trace_id=trace_id)

    if not trace_url:
        raise RuntimeError("Langfuse could not create the trace URL.")

    return trace_id, trace_url


def flush_traces() -> None:
    """Send pending trace data to Langfuse immediately."""
    langfuse.flush()
