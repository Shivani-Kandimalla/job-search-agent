"""
Filtering Tool (Section 3.1 of the assignment).

Deterministic, rule-based job filtering against the candidate's stated
preferences. No LLM call happens in this module. Every rejected job gets a
logged, human-readable reason so the report and trace can show exactly why
a posting was dropped.

Rules implemented (in this order):
  1. Company exclusion       -> reject if job's company is on the exclusion list
  2. Target job title match  -> reject if the job title doesn't correspond to
                                 one of the candidate's target roles
  3. Location preference     -> reject if the job's location doesn't match
                                 any preferred location (city/state/"Remote")
  4. Remote-only filter      -> only applied if preferences["remote_only"] is true
  5. Years of experience     -> reject if the job's minimum required years
                                 exceeds the candidate's years of experience

A job is only "kept" if it survives every rule.
"""

import csv
import json
import re
from dataclasses import dataclass, field


@dataclass
class FilterResult:
    kept: list = field(default_factory=list)
    rejected: list = field(default_factory=list)  # list of (job, reason) tuples


def _tokenize(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _title_matches(job_title: str, target_titles: list) -> bool:
    """A job title matches if the title's word set is a superset of ALL the
    words in at least one target title (order/punctuation independent).

    E.g. target "Machine Learning Engineer" (tokens: machine, learning,
    engineer) matches a job titled "Senior Machine Learning Engineer,
    Payments" because all three tokens are present.

    Target "AI Engineer" (tokens: ai, engineer) matches "Senior AI/ML
    Engineer - Multimodal..." because both "ai" and "engineer" appear as
    separate tokens once punctuation like "/" is split on.
    """
    job_tokens = _tokenize(job_title)
    for target in target_titles:
        target_tokens = _tokenize(target)
        if target_tokens.issubset(job_tokens):
            return True
    return False


def _location_matches(job_location: str, preferred_locations: list) -> bool:
    job_lower = job_location.lower()

    # "Remote" keyword match
    if "remote" in job_lower and any("remote" in p.lower() for p in preferred_locations):
        return True

    for pref in preferred_locations:
        pref_lower = pref.lower()
        # Direct substring match, e.g. preferred "San Francisco, CA" is
        # literally contained in "San Francisco, CA (Remote-friendly)"
        if pref_lower in job_lower:
            return True

        # State-level fallback match, e.g. preferred "San Francisco, CA"
        # (state "ca") still counts as a match for "Sunnyvale, CA (Hybrid)"
        # -- candidates usually mean "this general area", not one city.
        if "," in pref and "," in job_location:
            pref_state = pref.split(",")[-1].strip().lower()
            job_state_field = job_location.split(",")[-1].strip().lower()
            job_state_token = job_state_field.split()[0] if job_state_field else ""
            if pref_state and pref_state == job_state_token:
                return True

    return False


def _min_years_required(years_experience_str: str) -> int:
    """Extract the first integer found, e.g. '5+' -> 5, '2-3+' -> 2,
    '7+ (3+ hands-on MLOps)' -> 7. If nothing parses, default to 0
    (don't reject on a formatting quirk)."""
    match = re.search(r"\d+", years_experience_str)
    return int(match.group()) if match else 0


def filter_jobs(jobs: list, preferences: dict):
    """
    jobs: list of dicts (rows from data/jobs.csv)
    preferences: dict, expects the shape of data/persona_preferences.json's
                 "preferences" key, i.e.:
                 {
                   "preferred_locations": [...],
                   "remote_only": bool,
                   "years_of_experience": int,
                   "companies_to_exclude": [...],
                   "target_job_titles": [...]
                 }

    Returns: (kept: list[dict], rejected: list[dict]) where each rejected
    entry is the original job dict plus a "rejection_reason" key.
    """
    kept = []
    rejected = []

    excluded_companies = [c.lower() for c in preferences.get("companies_to_exclude", [])]
    target_titles = preferences.get("target_job_titles", [])
    preferred_locations = preferences.get("preferred_locations", [])
    remote_only = preferences.get("remote_only", False)
    candidate_years = preferences.get("years_of_experience", 0)

    for job in jobs:
        reason = None

        if any(excl in job["company"].lower() for excl in excluded_companies):
            reason = f"Company '{job['company']}' is on the exclusion list."

        elif target_titles and not _title_matches(job["title"], target_titles):
            reason = (
                f"Job title '{job['title']}' does not match any target job "
                f"title in preferences ({', '.join(target_titles)})."
            )

        elif preferred_locations and not _location_matches(job["location"], preferred_locations):
            reason = (
                f"Location '{job['location']}' does not match any preferred "
                f"location ({', '.join(preferred_locations)})."
            )

        elif remote_only and "remote" not in job["location"].lower():
            reason = f"Remote-only preference set, but location '{job['location']}' is not remote."

        else:
            min_years = _min_years_required(job["years_experience"])
            if min_years > candidate_years:
                reason = (
                    f"Requires {min_years}+ years of experience "
                    f"(job lists '{job['years_experience']}'), candidate has {candidate_years}."
                )

        if reason:
            rejected_job = dict(job)
            rejected_job["rejection_reason"] = reason
            rejected.append(rejected_job)
        else:
            kept.append(dict(job))

    return kept, rejected


def load_jobs(csv_path: str) -> list:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_preferences(json_path: str) -> dict:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    return data["preferences"]


if __name__ == "__main__":
    import os

    base = os.path.join(os.path.dirname(__file__), "..", "..")
    jobs = load_jobs(os.path.join(base, "data", "jobs.csv"))
    preferences = load_preferences(os.path.join(base, "data", "persona_preferences.json"))

    kept, rejected = filter_jobs(jobs, preferences)

    print(f"KEPT ({len(kept)}):")
    for j in kept:
        print(f"  [{j['job_id']}] {j['title']} @ {j['company']} ({j['location']})")

    print(f"\nREJECTED ({len(rejected)}):")
    for j in rejected:
        print(f"  [{j['job_id']}] {j['title']} @ {j['company']} -> {j['rejection_reason']}")
