from __future__ import annotations

import os
import re
import time
from typing import Callable

import requests


FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


def normalize(value: str | None) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def build_query(facility: dict) -> str:
    parts = [
        facility.get("facility"),
        facility.get("street_address"),
        facility.get("city"),
        facility.get("state"),
        facility.get("zip"),
    ]

    return " ".join(
        str(p).strip()
        for p in parts
        if p is not None and str(p).strip()
    )


def find_place_candidates(query: str, api_key: str) -> list[dict]:
    params = {
        "input": query,
        "inputtype": "textquery",
        "fields": "place_id,name,formatted_address",
        "key": api_key,
    }

    response = requests.get(
        FIND_PLACE_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()
    payload = response.json()

    if payload.get("status") != "OK":
        raise RuntimeError(
            f"Google Find Place error: "
            f"{payload.get('status')} "
            f"{payload.get('error_message', '')}"
        )

    return payload.get("candidates", [])


def pick_best_candidate(
    candidates: list[dict],
    city: str,
    state: str,
) -> dict | None:

    if not candidates:
        return None

    city_n = normalize(city)
    state_n = normalize(state)

    def score(candidate: dict) -> int:
        address = normalize(
            candidate.get("formatted_address", "")
        )

        value = 0

        if city_n and city_n in address:
            value += 2

        if state_n and state_n in address:
            value += 2

        return value

    return max(candidates, key=score)


def get_place_details(
    place_id: str,
    api_key: str,
) -> dict:

    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,rating,user_ratings_total",
        "key": api_key,
    }

    response = requests.get(
        DETAILS_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()
    payload = response.json()

    if payload.get("status") != "OK":
        raise RuntimeError(
            f"Google Place Details error: "
            f"{payload.get('status')} "
            f"{payload.get('error_message', '')}"
        )

    return payload.get("result", {})


def run_google_report(
    facilities: list[dict],
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[dict]:

    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "GOOGLE_PLACES_API_KEY is not configured."
        )

    output = []
    total = len(facilities)

    for idx, facility in enumerate(facilities, start=1):

        name = facility["facility"]

        rating = None
        review_count = None
        notes = ""

        try:
            # Use saved Place ID if we already have one
            place_id = facility.get("google_place_id")

            if not place_id:
                query = build_query(facility)

                candidates = find_place_candidates(
                    query,
                    api_key,
                )

                best = pick_best_candidate(
                    candidates,
                    facility.get("city", ""),
                    facility.get("state", ""),
                )

                if not best:
                    raise RuntimeError(
                        "No matching Google Place found"
                    )

                place_id = best.get("place_id")

            details = get_place_details(
                place_id,
                api_key,
            )

            rating = details.get("rating")
            review_count = details.get(
                "user_ratings_total"
            )

        except Exception as exc:
            notes = f"Google error: {exc}"
            print(
                f"GOOGLE ERROR — {name}: {exc}"
            )

        output.append({
            "State": facility["state"],
            "Facility": name,
            "Google Rating": rating,
            "Google Review Count": review_count,
            "Notes": notes,
        })

        if progress_callback:
            progress_callback(
                idx,
                total,
                name,
            )

        time.sleep(0.2)

    return output