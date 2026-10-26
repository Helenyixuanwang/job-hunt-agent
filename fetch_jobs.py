"""Step 1: fetch job postings from Adzuna that match search_profile.yaml.

Run:  python fetch_jobs.py
Output: a list in the terminal, plus jobs.json (used by step 2 for scoring).
"""
import json
import os
import sys

import requests
import yaml
from dotenv import load_dotenv

ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"


def load_profile(path="search_profile.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch(role, search, profile, app_id, app_key):
    """Return raw Adzuna results for one role in one search (location)."""
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": role,
        "results_per_page": profile.get("results_per_search", 20),
        "max_days_old": profile.get("max_days_old", 14),
        "sort_by": "date",
        "content-type": "application/json",
    }
    if search.get("where"):
        params["where"] = search["where"]
        params["distance"] = search.get("distance_km", 25)
    if search.get("remote"):
        params["what_and"] = "remote"
    if profile.get("exclude_keywords"):
        params["what_exclude"] = " ".join(profile["exclude_keywords"])

    url = ADZUNA_URL.format(country=profile.get("country", "ca"))
    response = requests.get(url, params=params, timeout=20)
    if response.status_code != 200:
        print(f"  Adzuna error: {response.status_code} {response.text[:200]}")
        return []
    return response.json().get("results", [])


def simplify(result, role, search_label):
    """Keep only the fields we need later."""
    return {
        "id": result.get("id"),
        "title": result.get("title", "").strip(),
        "company": result.get("company", {}).get("display_name", "Unknown"),
        "location": result.get("location", {}).get("display_name", ""),
        "posted": result.get("created", "")[:10],
        "salary_min": result.get("salary_min"),
        "salary_max": result.get("salary_max"),
        "url": result.get("redirect_url"),
        "description": result.get("description", ""),
        "matched_role": role,
        "found_in": search_label,
    }


def main():
    load_dotenv()
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        sys.exit("Missing ADZUNA_APP_ID or ADZUNA_APP_KEY in your .env file.")

    profile = load_profile()
    searches = profile.get("searches") or [{"label": "All of country"}]

    jobs = {}
    for search in searches:
        label = search.get("label", search.get("where", "search"))
        for role in profile["roles"]:
            print(f"Searching: {role} | {label} ...")
            for result in fetch(role, search, profile, app_id, app_key):
                job = simplify(result, role, label)
                jobs.setdefault(job["id"], job)  # skip duplicates across searches

    jobs = sorted(jobs.values(), key=lambda j: j["posted"], reverse=True)

    print(f"\nFound {len(jobs)} unique postings:\n")
    for i, job in enumerate(jobs, 1):
        salary = ""
        if job["salary_min"]:
            salary = f"  ${job['salary_min']:,.0f}–${job['salary_max']:,.0f}"
        print(f"{i:2}. {job['title']} — {job['company']}")
        print(f"    {job['location']} | {job['found_in']} | posted {job['posted']}{salary}")
        print(f"    {job['url']}\n")

    with open("jobs.json", "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)
    print("Saved to jobs.json")


if __name__ == "__main__":
    main()
