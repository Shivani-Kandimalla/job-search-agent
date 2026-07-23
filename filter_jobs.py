"""
Simple CSV job filter.

Loads jobs.csv and filters rows by location (case-insensitive,
substring match), with basic validation of user-supplied input.

Usage:
    python filter_jobs.py <location>
    python filter_jobs.py "New York"
    python filter_jobs.py            # prompts interactively
"""

import csv
import os
import sys

CSV_PATH = "jobs.csv"
MAX_QUERY_LEN = 100


def validate_location(raw_input: str) -> str:
    """Validate and sanitize the location filter provided by the user."""
    if raw_input is None:
        raise ValueError("Location cannot be None.")

    cleaned = raw_input.strip()

    if not cleaned:
        raise ValueError("Location cannot be empty.")

    if len(cleaned) > MAX_QUERY_LEN:
        raise ValueError(f"Location must be {MAX_QUERY_LEN} characters or fewer.")

    # Only allow letters, numbers, spaces, commas, hyphens, and periods.
    # Blocks stray characters that have no business being in a place name
    # (basic defense against odd/malicious input, not a security boundary).
    allowed = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,.-"
    )
    if not all(ch in allowed for ch in cleaned):
        raise ValueError("Location contains unsupported characters.")

    return cleaned


def load_jobs(csv_path: str) -> list[dict]:
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "location" not in reader.fieldnames:
            raise ValueError("CSV is missing a 'location' column.")
        return list(reader)


def filter_by_location(jobs: list[dict], location: str) -> list[dict]:
    location_lower = location.lower()
    return [job for job in jobs if location_lower in job.get("location", "").lower()]


def main() -> None:
    raw_arg = sys.argv[1] if len(sys.argv) > 1 else input("Filter jobs by location: ")

    try:
        location = validate_location(raw_arg)
        jobs = load_jobs(CSV_PATH)
        results = filter_by_location(jobs, location)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    if not results:
        print(f"No jobs found for location containing '{location}'.")
        return

    print(f"Found {len(results)} job(s) matching '{location}':\n")
    for job in results:
        print(f"- {job['title']} at {job['company']} ({job['location']}) "
              f"- ${job['salary']} - {job['job_type']}")


if __name__ == "__main__":
    main()
