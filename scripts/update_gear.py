#!/usr/bin/env python3
"""Fetch Blafych's public Raider.IO snapshot without Blizzard credentials."""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
CHARACTER = {"region": "eu", "realm": "gordunni", "name": "Блафыч"}
PROFILE_FIELDS = [
    "gear",
    "talents",
    "raid_progression",
    "mythic_plus_scores_by_season:current",
    "mythic_plus_best_runs:all",
    "mythic_plus_recent_runs",
    "mythic_plus_weekly_highest_level_runs",
    "mythic_plus_previous_weekly_highest_level_runs",
    "mythic_plus_ranks",
]
PROFILE_URL = "https://raider.io/api/v1/characters/profile?" + urlencode({
    **CHARACTER, "fields": ",".join(PROFILE_FIELDS)
})
AFFIX_URL = "https://raider.io/api/v1/mythic-plus/affixes?" + urlencode({
    "region": "eu", "locale": "en"
})


def fetch_json(url, attempts=4):
    request = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "BlafychGearTracker/2.0 (personal, Raider.IO API; GitHub)",
    })
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=35) as response:
                return json.load(response)
        except HTTPError as exc:
            if attempt == attempts - 1 or (exc.code != 429 and not 500 <= exc.code < 600):
                raise
            header = exc.headers.get("Retry-After", "")
            delay = min(90, int(header)) if header.isdigit() else 5 * (attempt + 1)
            print(f"Raider.IO HTTP {exc.code}: waiting {delay}s", flush=True)
            time.sleep(delay)
        except (URLError, TimeoutError):
            if attempt == attempts - 1:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("API attempts exhausted")


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(path.suffix + ".tmp")
    staging.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(staging, path)


def main():
    source = fetch_json(PROFILE_URL)
    if not isinstance(source, dict) or str(source.get("name", "")).casefold() != CHARACTER["name"].casefold():
        raise ValueError("Raider.IO returned wrong character or invalid response")
    gear = source.get("gear")
    if not isinstance(gear, dict) or not isinstance(gear.get("items"), dict) or not gear["items"]:
        raise ValueError("No equipped gear returned; previous snapshot was not modified")
    if not isinstance(source.get("mythic_plus_best_runs"), list):
        raise ValueError("No Mythic+ field returned; previous snapshot was not modified")

    mplus = {
        "scores_by_season": source.get("mythic_plus_scores_by_season", []),
        "best_runs": source.get("mythic_plus_best_runs", []),
        "recent_runs": source.get("mythic_plus_recent_runs", []),
        "weekly_highest_level_runs": source.get("mythic_plus_weekly_highest_level_runs", []),
        "previous_weekly_highest_level_runs": source.get("mythic_plus_previous_weekly_highest_level_runs", []),
        "ranks": source.get("mythic_plus_ranks", {}),
    }

    affixes = None
    affixes_error = None
    try:
        affixes = fetch_json(AFFIX_URL, attempts=2)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        affixes_error = f"{type(exc).__name__}: {exc}"
        print(f"Optional affixes unavailable: {affixes_error}", flush=True)

    snapshot = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_last_crawled_at": source.get("last_crawled_at"),
        "source_api_url": PROFILE_URL,
        "character": {
            "name": source.get("name"),
            "realm": source.get("realm"),
            "region": source.get("region", CHARACTER["region"]),
            "class": source.get("class"),
            "active_spec_name": source.get("active_spec_name"),
            "profile_url": source.get("profile_url"),
        },
        "gear": gear,
        "mythic_plus": mplus,
        "talents": source.get("talents"),  # May be absent for an unindexed loadout.
        "raid_progression": source.get("raid_progression"),  # May be absent/empty.
        "weekly_affixes": affixes,
        "weekly_affixes_error": affixes_error,
    }
    atomic_json(ROOT / "gear.json", snapshot)
    print(
        f"Fetched {source.get('name')}, equipped ilvl {gear.get('item_level_equipped')}, "
        f"{len(mplus['best_runs'])} best M+ runs; "
        f"talents {'present' if source.get('talents') else 'missing'}, "
        f"raids {'present' if source.get('raid_progression') else 'missing'}",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
