from __future__ import annotations

import calendar
import os
import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Callable
from zoneinfo import ZoneInfo

import requests

GRAPH_ROOT = "https://graph.facebook.com"
CENTRAL = ZoneInfo("America/Chicago")


def normalize(value: str | None) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def graph_url(path: str) -> str:
    version = os.getenv("META_GRAPH_VERSION", "").strip()
    if not version:
        raise RuntimeError("META_GRAPH_VERSION is not configured (example: vXX.X).")
    return f"{GRAPH_ROOT}/{version}/{path.lstrip('/')}"


def get_pages(user_token: str) -> list[dict]:
    url = graph_url("me/accounts")
    params = {
        "access_token": user_token,
        "limit": 100,
        "fields": "name,id,access_token",
    }
    pages = []
    while url:
        r = requests.get(url, params=params, timeout=30)

        if not r.ok:
            try:
                error_data = r.json()
            except Exception:
                error_data = r.text
        
            raise RuntimeError(
                f"Meta API error {r.status_code}: {error_data}"
            )
        
        payload = r.json()
        if "error" in payload:
            raise RuntimeError(payload["error"].get("message", "Meta API error"))
        pages.extend(payload.get("data", []))
        url = payload.get("paging", {}).get("next")
        params = {}
    return pages


def choose_page(facility: dict, pages: list[dict]) -> dict | None:
    saved = facility.get("facebook_page_id")
    if saved:
        for p in pages:
            if str(p.get("id")) == str(saved):
                return p

    target = normalize(facility.get("facility"))
    exact = [p for p in pages if normalize(p.get("name")) == target]
    if exact:
        return exact[0]

    scored = []
    for page in pages:
        ratio = SequenceMatcher(None, target, normalize(page.get("name"))).ratio()
        scored.append((ratio, page))
    if not scored:
        return None
    ratio, page = max(scored, key=lambda x: x[0])
    return page if ratio >= 0.82 else None


def month_bounds(year: int, month: int) -> tuple[int, int]:
    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=CENTRAL)
    last_day = calendar.monthrange(year, month)[1]
    end_local = datetime(year, month, last_day, 23, 59, 59, tzinfo=CENTRAL)
    return int(start_local.astimezone(timezone.utc).timestamp()), int(end_local.astimezone(timezone.utc).timestamp())


def count_items(page_id: str, page_token: str, edge: str, since: int, until: int) -> int:
    url = graph_url(f"{page_id}/{edge}")
    params = {
        "access_token": page_token,
        "fields": "created_time",
        "limit": 100,
        "since": since,
        "until": until,
    }
    count = 0
    while url:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        payload = r.json()
        if "error" in payload:
            raise RuntimeError(payload["error"].get("message", "Meta API error"))
        count += len(payload.get("data", []))
        url = payload.get("paging", {}).get("next")
        params = {}
    return count


def get_page_metrics(page: dict, year: int, month: int) -> tuple[int | None, int]:
    page_id = page["id"]
    token = page["access_token"]

    r = requests.get(
        graph_url(page_id),
        params={
            "access_token": token,
            "fields": "name,followers_count",
        },
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    if "error" in payload:
        raise RuntimeError(payload["error"].get("message", "Meta API error"))

    # likes = payload.get("fan_count")
    followers = payload.get("followers_count")

    since, until = month_bounds(year, month)
    posts = count_items(page_id, token, "published_posts", since, until)
    # videos = count_items(page_id, token, "videos", since, until)
    return followers, posts


def run_facebook_report(
    facilities: list[dict],
    year: int,
    month: int,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[dict]:
    user_token = os.getenv("META_USER_ACCESS_TOKEN", "").strip()
    if not user_token:
        raise RuntimeError("META_USER_ACCESS_TOKEN is not configured on the server.")

    pages = get_pages(user_token)
    output = []
    total = len(facilities)

    for idx, facility in enumerate(facilities, start=1):
        name = facility["facility"]
        followers = None
        posts = 0
        notes = ""

        try:
            page = choose_page(facility, pages)
            if not page:
                notes = "No matching Facebook Page found"
            else:
                followers, posts = get_page_metrics(page, year, month)
        except Exception as exc:
            notes = f"Facebook error: {exc}"

        output.append({
            "State": facility["state"],
            "Facility": name,
            "Facebook Followers": followers,
            "Facebook Posts (Target Month)": posts,
            "Notes": notes,
        })

        if progress_callback:
            progress_callback(idx, total, name)
        time.sleep(0.2)

    return output
