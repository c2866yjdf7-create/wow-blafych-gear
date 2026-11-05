#!/usr/bin/env python3
"""Save public Raider.IO equipment data for Blafych (EU / Gordunni)."""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REGION = "eu"
REALM = "gordunni"
NAME = "Блафыч"
API = "https://raider.io/api/v1/characters/profile"
FIELDS = ",".join((
    "gear",
    "mythic_plus_scores_by_season:current",
    "mythic_plus_best_runs:all",
    "mythic_plus_recent_runs",
    "mythic_plus_weekly_highest_level_runs",
    "mythic_plus_ranks",
))
PARAMS = {"region": REGION, "realm": REALM, "name": NAME, "fields": FIELDS}
URL = f"{API}?{urlencode(PARAMS)}"
OUTPUT = Path(__file__).resolve().parent.parent / "gear.json"


def fetch_profile():
    request = Request(
        URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "wow-blafych-gear/1.0 (personal character snapshot)",
        },
    )
    for attempt in range(4):
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            if (exc.code == 429 or 500 <= exc.code < 600) and attempt < 3:
                retry_after = exc.headers.get("Retry-After", "")
                delay = min(90, int(retry_after)) if retry_after.isdigit() else 5 * (attempt + 1)
                print(f"Raider.IO returned HTTP {exc.code}; retrying in {delay}s", flush=True)
                time.sleep(delay)
                continue
            raise
        except (URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("Unable to fetch Raider.IO profile")


def main():
    source = fetch_profile()
    if not isinstance(source, dict):
        raise ValueError("API returned a non-object response")
    if str(source.get("name", "")).casefold() != NAME.casefold():
        raise ValueError(f"Wrong character returned by API: {source.get('name')!r}")
    gear = source.get("gear")
    if not isinstance(gear, dict) or not isinstance(gear.get("items"), dict) or not gear["items"]:
        raise ValueError("No equipped gear in Raider.IO response; keeping previous snapshot")

    mplus_fields = (
        "mythic_plus_scores_by_season",
        "mythic_plus_best_runs",
        "mythic_plus_recent_runs",
        "mythic_plus_weekly_highest_level_runs",
        "mythic_plus_ranks",
    )
    if not any(field in source for field in mplus_fields):
        raise ValueError("Raider.IO returned no Mythic+ fields; keeping previous snapshot")

    mythic_plus = {
        "scores_by_season": source.get("mythic_plus_scores_by_season", []),
        "best_runs": source.get("mythic_plus_best_runs", []),
        "recent_runs": source.get("mythic_plus_recent_runs", []),
        "weekly_highest_level_runs": source.get("mythic_plus_weekly_highest_level_runs", []),
        "ranks": source.get("mythic_plus_ranks", {}),
    }

    snapshot = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_last_crawled_at": source.get("last_crawled_at"),
        "source_api_url": URL,
        "character": {
            "name": source.get("name"),
            "realm": source.get("realm"),
            "region": source.get("region", REGION),
            "class": source.get("class"),
            "active_spec_name": source.get("active_spec_name"),
            "profile_url": source.get("profile_url"),
        },
        "gear": gear,
        "mythic_plus": mythic_plus,
    }
    temp = OUTPUT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, OUTPUT)
    print(
        f"Saved {len(gear['items'])} items, "
        f"equipped ilvl {gear.get('item_level_equipped')}, "
        f"best M+ runs {len(mythic_plus['best_runs'])}, "
        f"source crawled {source.get('last_crawled_at')}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
