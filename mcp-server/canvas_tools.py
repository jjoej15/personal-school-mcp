import os
from datetime import date, datetime, timezone
from typing import Literal

import httpx

from utils import (
    day_window_utc,
    format_iso_utc,
    parse_iso_datetime,
    parse_link_header,
    week_window_utc,
)

CANVAS_TOKEN_ENV = "CANVAS_API_TOKEN"
CANVAS_BASE_URL_ENV = "CANVAS_BASE_URL"
CANVAS_DEFAULT_PER_PAGE = 100

def _canvas_api_base() -> str:
    base_url = os.getenv(CANVAS_BASE_URL_ENV, "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError(
            f"missing Canvas base URL. Set {CANVAS_BASE_URL_ENV} in .env"
        )

    if base_url.endswith("/api/v1"):
        return base_url

    return f"{base_url}/api/v1"


def _canvas_headers() -> dict[str, str]:
    token = os.getenv(CANVAS_TOKEN_ENV, "").strip()
    if not token:
        raise RuntimeError(f"missing Canvas token. Set {CANVAS_TOKEN_ENV} in .env")

    return {"Authorization": f"Bearer {token}"}


def _canvas_get_all(path: str, params: dict[str, object] | None = None) -> list[dict[str, object]]:
    base_url = _canvas_api_base()
    headers = _canvas_headers()
    next_url: str | None = f"{base_url}/{path.lstrip('/')}"
    query_params: dict[str, object] | None = dict(params or {})
    if query_params is not None and "per_page" not in query_params:
        query_params["per_page"] = CANVAS_DEFAULT_PER_PAGE

    items: list[dict[str, object]] = []
    with httpx.Client(timeout=20.0, headers=headers) as client:
        while next_url:
            response = client.get(next_url, params=query_params)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Canvas API request failed ({response.status_code}): {response.text}"
                )

            payload = response.json()
            if isinstance(payload, list):
                items.extend(payload)
            else:
                raise RuntimeError("Canvas API response was not a list as expected")

            links = parse_link_header(response.headers.get("Link"))
            next_url = links.get("next")
            query_params = None

    return items


def _canvas_get_one(path: str, params: dict[str, object] | None = None) -> dict[str, object]:
    base_url = _canvas_api_base()
    headers = _canvas_headers()
    url = f"{base_url}/{path.lstrip('/')}"

    with httpx.Client(timeout=20.0, headers=headers) as client:
        response = client.get(url, params=params)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Canvas API request failed ({response.status_code}): {response.text}"
            )

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Canvas API response was not an object as expected")

    return payload


def _active_courses() -> list[dict[str, object]]:
    return _canvas_get_all(
        "users/self/courses",
        {
            "enrollment_state": "active",
            "state[]": ["available", "completed"],
        },
    )


def _collect_assignments() -> list[dict[str, object]]:
    assignments: list[dict[str, object]] = []

    for course in _active_courses():
        course_id = course.get("id")
        if course_id is None:
            continue

        course_name = str(course.get("name") or "Unknown Course")
        course_assignments = _canvas_get_all(
            f"courses/{course_id}/assignments",
            {
                "bucket": "unsubmitted",
                "include[]": ["submission"],
            },
        )
        for assignment in course_assignments:
            assignment["course_id"] = course_id
            assignment["course_name"] = course_name
            assignments.append(assignment)

        submitted_assignments = _canvas_get_all(
            f"courses/{course_id}/assignments",
            {
                "bucket": "past",
                "include[]": ["submission"],
            },
        )
        for assignment in submitted_assignments:
            assignment["course_id"] = course_id
            assignment["course_name"] = course_name
            assignments.append(assignment)

    return assignments


def _dedupe_assignments(assignments: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: dict[tuple[object, object], dict[str, object]] = {}
    for assignment in assignments:
        key = (assignment.get("course_id"), assignment.get("id"))
        deduped[key] = assignment
    return list(deduped.values())


def _assignment_summary(assignment: dict[str, object]) -> dict[str, object]:
    return {
        "assignment_id": assignment.get("id"),
        "name": assignment.get("name"),
        "course_id": assignment.get("course_id"),
        "course_name": assignment.get("course_name"),
        "due_at": assignment.get("due_at"),
        "points_possible": assignment.get("points_possible"),
        "html_url": assignment.get("html_url"),
    }


def _find_assignment_candidates(assignment_name: str) -> list[dict[str, object]]:
    needle = assignment_name.strip().lower()
    if not needle:
        raise ValueError("assignment_name must not be empty")

    matches: list[dict[str, object]] = []
    for assignment in _dedupe_assignments(_collect_assignments()):
        candidate_name = str(assignment.get("name") or "").lower()
        if needle in candidate_name:
            matches.append(assignment)

    return matches


def _filter_assignments_in_window(
    start_dt: datetime | None,
    end_dt: datetime | None,
) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for assignment in _dedupe_assignments(_collect_assignments()):
        due_at = assignment.get("due_at")
        if not isinstance(due_at, str) or not due_at:
            continue

        due_dt = parse_iso_datetime(due_at)
        if start_dt is not None and due_dt < start_dt:
            continue

        if end_dt is not None and due_dt >= end_dt:
            continue

        matches.append(assignment)

    matches.sort(key=lambda item: str(item.get("due_at") or ""))
    return matches


def _resolve_assignment_window(
    time_window: Literal["upcoming", "day", "week", "custom"],
    target_date: str | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[datetime | None, datetime | None]:
    if time_window == "upcoming":
        return datetime.now(timezone.utc), None

    if time_window == "day":
        if not target_date:
            raise ValueError("date is required when time_window is 'day'")
        day_value = date.fromisoformat(target_date)
        return day_window_utc(day_value)

    if time_window == "week":
        if not target_date:
            raise ValueError("date is required when time_window is 'week'")
        day_value = date.fromisoformat(target_date)
        return week_window_utc(day_value)

    if time_window == "custom":
        if not start_date or not end_date:
            raise ValueError(
                "start_date and end_date are required when time_window is 'custom'"
            )
        start_day = date.fromisoformat(start_date)
        end_day = date.fromisoformat(end_date)
        start_dt, _ = day_window_utc(start_day)
        _, end_dt = day_window_utc(end_day)
        if end_dt <= start_dt:
            raise ValueError("end_date must be on or after start_date")
        return start_dt, end_dt

    raise ValueError("time_window must be one of: upcoming, day, week, custom")


def _build_assignment_details(
    assignment: dict[str, object],
    include_description: bool,
    include_grade: bool,
) -> dict[str, object]:
    details = _assignment_summary(assignment)

    if include_description:
        details["description"] = assignment.get("description")

    if include_grade:
        course_id = assignment.get("course_id")
        assignment_id = assignment.get("id")
        if course_id is None or assignment_id is None:
            details["grade_error"] = "assignment missing required IDs"
        else:
            submission = _canvas_get_one(
                f"courses/{course_id}/assignments/{assignment_id}/submissions/self"
            )
            details["grade"] = {
                "grade": submission.get("grade"),
                "score": submission.get("score"),
                "submitted_at": submission.get("submitted_at"),
                "late": submission.get("late"),
                "missing": submission.get("missing"),
                "workflow_state": submission.get("workflow_state"),
            }

    return details


def register_canvas_tools(mcp) -> None:
    @mcp.tool
    def canvas_get_schedule(
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        """
        Returns Canvas calendar events for a date range.
        Dates should be in YYYY-MM-DD format.
        """
        if limit <= 0:
            raise ValueError("limit must be greater than 0")

        params: dict[str, object] = {"all_events": "true"}

        if start_date:
            start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
            params["start_date"] = format_iso_utc(start_dt)

        if end_date:
            end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
            params["end_date"] = format_iso_utc(end_dt)

        events = _canvas_get_all("calendar_events", params)
        events.sort(
            key=lambda event: str(event.get("start_at") or event.get("created_at") or "")
        )

        trimmed = events[:limit]
        return [
            {
                "id": event.get("id"),
                "title": event.get("title"),
                "description": event.get("description"),
                "start_at": event.get("start_at"),
                "end_at": event.get("end_at"),
                "html_url": event.get("html_url"),
                "context_code": event.get("context_code"),
            }
            for event in trimmed
        ]


    @mcp.tool
    def canvas_get_assignments(
        time_window: Literal["upcoming", "day", "week", "custom"] = "upcoming",
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        """
        Returns assignments by due-date window.

        - time_window='upcoming': assignments due from now onward.
        - time_window='day': assignments due on date (YYYY-MM-DD).
        - time_window='week': assignments due in the week containing date (YYYY-MM-DD).
        - time_window='custom': assignments due from start_date through end_date (YYYY-MM-DD).
        """
        if limit <= 0:
            raise ValueError("limit must be greater than 0")

        start_dt, end_dt = _resolve_assignment_window(
            time_window=time_window,
            target_date=date,
            start_date=start_date,
            end_date=end_date,
        )

        matches = _filter_assignments_in_window(start_dt, end_dt)
        return [_assignment_summary(item) for item in matches[:limit]]


    @mcp.tool
    def canvas_get_assignment_details(
        assignment_name: str,
        include_description: bool = False,
        include_grade: bool = False,
    ) -> dict[str, object]:
        """
        Returns assignment details for a specific assignment name.

        Core summary fields (including due_at) are always returned.
        Set include_description/include_grade to return additional fields.
        """
        matches = _find_assignment_candidates(assignment_name)
        if not matches:
            return {"found": False, "matches": []}

        if len(matches) > 1:
            return {
                "found": False,
                "message": "multiple assignments matched; refine assignment_name",
                "matches": [_assignment_summary(item) for item in matches[:10]],
            }

        assignment = matches[0]
        return {
            "found": True,
            "assignment": _build_assignment_details(
                assignment,
                include_description=include_description,
                include_grade=include_grade,
            ),
        }
