"""Step 2: have Claude score each posting in jobs.json against your resume.

Run:  python score_jobs.py
Needs: jobs.json (from step 1), resume.md, ANTHROPIC_API_KEY in .env
Output: ranked list in the terminal, plus scored_jobs.json
"""
import json
import os
import sys

import anthropic
import yaml
from dotenv import load_dotenv

DEFAULT_MODEL = "claude-haiku-5-5"  # fast and cheap; switch to claude-sonnet-5-5 for sharper judgment

# Claude must answer by "calling" this tool, which guarantees clean JSON back.
SCORE_TOOL = {
    "name": "record_job_score",
    "description": "Record how well one job posting fits the candidate.",
    "input_schema": {
        "type": "object",
        "properties": {
            "fit_score": {
                "type": "integer",
                "description": "0-100. How well the candidate fits AND matches what they are looking for.",
            },
            "remote": {
                "type": "string",
                "enum": ["yes", "no", "unclear"],
                "description": "Is the role actually remote-friendly for someone in Canada?",
            },
            "level": {
                "type": "string",
                "enum": ["intern/co-op", "new grad", "junior/mid", "senior", "lead/staff+", "unclear"],
            },
            "reasons": {
                "type": "string",
                "description": "One or two sentences on why this score.",
            },
            "missing_skills": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Skills the posting asks for that the resume does not show.",
            },
        },
        "required": ["fit_score", "remote", "level", "reasons", "missing_skills"],
    },
}


def load_inputs():
    with open("search_profile.yaml", encoding="utf-8") as f:
        profile = yaml.safe_load(f)
    try:
        with open("resume.md", encoding="utf-8") as f:
            resume = f.read()
    except FileNotFoundError:
        sys.exit("Missing resume.md — paste your resume as plain text into resume.md first.")
    try:
        with open("jobs.json", encoding="utf-8") as f:
            jobs = json.load(f)
    except FileNotFoundError:
        sys.exit("Missing jobs.json — run python fetch_jobs.py first.")
    return profile, resume, jobs


def dedupe(jobs):
    """Drop the same title at the same company posted in several cities."""
    seen, unique = set(), []
    for job in jobs:
        key = (job["title"].lower(), job["company"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def score_job(client, model, profile, resume, job):
    prompt = f"""You are screening job postings for a job seeker.

WHAT THEY ARE LOOKING FOR:
- Roles: {", ".join(profile["roles"])}
- Location: {profile.get("location_preference", "no preference")}
- Notes: {profile.get("notes", "none")}

THEIR RESUME:
{resume}

JOB POSTING:
Title: {job["title"]}
Company: {job["company"]}
Location: {job["location"]} (found in search: {job.get("found_in", "unknown")})
Description (may be a short excerpt): {job["description"]}

Score the fit. Give a low score if the level, role type, or location
clearly doesn't match what they are looking for, even if the skills match.
A posting found in a "remote" search only mentions the word "remote"
somewhere; judge from the text whether the role is truly remote."""

    response = client.messages.create(
        model=model,
        max_tokens=500,
        tools=[SCORE_TOOL],
        tool_choice={"type": "tool", "name": "record_job_score"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise ValueError("Claude did not return a score")


def main():
    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("Missing ANTHROPIC_API_KEY in your .env file.")

    profile, resume, jobs = load_inputs()
    model = profile.get("model", DEFAULT_MODEL)
    min_score = profile.get("min_fit_score", 60)
    client = anthropic.Anthropic()

    jobs = dedupe(jobs)
    print(f"Scoring {len(jobs)} postings with {model} ...\n")

    scored = []
    for i, job in enumerate(jobs, 1):
        try:
            result = score_job(client, model, profile, resume, job)
        except Exception as e:  # keep going if one posting fails
            print(f"  [{i}/{len(jobs)}] skipped {job['title']}: {e}")
            continue
        job.update(result)
        scored.append(job)
        print(f"  [{i}/{len(jobs)}] {result['fit_score']:3}  {job['title']} — {job['company']}")

    scored.sort(key=lambda j: j["fit_score"], reverse=True)
    with open("scored_jobs.json", "w", encoding="utf-8") as f:
        json.dump(scored, f, indent=2, ensure_ascii=False)

    top = [j for j in scored if j["fit_score"] >= min_score]
    print(f"\n=== {len(top)} postings scored {min_score}+ ===\n")
    for job in top:
        print(f"{job['fit_score']:3}  {job['title']} — {job['company']}")
        print(f"     remote: {job['remote']} | level: {job['level']}")
        print(f"     {job['reasons']}")
        if job["missing_skills"]:
            print(f"     gaps: {', '.join(job['missing_skills'])}")
        print(f"     {job['url']}\n")
    print("Full results saved to scored_jobs.json")


if __name__ == "__main__":
    main()
