import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from utils import day_window_utc, format_iso_utc, week_window_utc

GOOGLE_CALENDAR_SCOPES_ENV = "GOOGLE_CALENDAR_SCOPES"
GOOGLE_CALENDAR_CREDENTIALS_FILE_ENV = "GOOGLE_CALENDAR_CREDENTIALS_FILE"
GOOGLE_CALENDAR_TOKEN_FILE_ENV = "GOOGLE_CALENDAR_TOKEN_FILE"
GOOGLE_CALENDAR_DEFAULT_LIMIT = 100

def _google_calendar_scopes() -> list[str]:
    raw_scopes = os.getenv(
        GOOGLE_CALENDAR_SCOPES_ENV,
        "https://www.googleapis.com/auth/calendar.readonly",
    )
    scopes = [scope.strip() for scope in raw_scopes.split(",") if scope.strip()]
    if not scopes:
        raise RuntimeError(
            "missing Google Calendar scopes. Set GOOGLE_CALENDAR_SCOPES in .env"
        )
    return scopes


def _load_google_credentials() -> ServiceAccountCredentials | UserCredentials:
    scopes = _google_calendar_scopes()

    credentials_file = os.getenv(GOOGLE_CALENDAR_CREDENTIALS_FILE_ENV, "").strip()
    token_file = os.getenv(GOOGLE_CALENDAR_TOKEN_FILE_ENV, "token.json").strip()

    oauth_credentials_path = Path(credentials_file) if credentials_file else None
    token_path = Path(token_file)
    creds: UserCredentials | None = None
    if token_path.exists():
        try:
            creds = UserCredentials.from_authorized_user_file(str(token_path), scopes)
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Google Calendar token file is invalid: {token_path}. Delete it and re-authenticate."
            ) from exc

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if oauth_credentials_path:
        if not oauth_credentials_path.exists():
            raise RuntimeError(
                f"Google Calendar OAuth credentials file not found: {oauth_credentials_path}"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(oauth_credentials_path),
            scopes,
        )
        creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    raise RuntimeError(
        "missing Google Calendar auth. Set GOOGLE_CALENDAR_CREDENTIALS_FILE for OAuth "
        "or GOOGLE_CALENDAR_SERVICE_ACCOUNT_FILE for service accounts"
    )


def _calendar_service():
    credentials = _load_google_credentials()
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _all_calendar_list_items(service) -> list[dict[str, object]]:
    calendars: list[dict[str, object]] = []
    page_token: str | None = None

    while True:
        response = service.calendarList().list(pageToken=page_token).execute()
        calendars.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return calendars


def _resolve_calendar_id(service, calendar_id: str | None, calendar_name: str | None) -> str:
    if calendar_id:
        return calendar_id

    if not calendar_name:
        return "primary"

    needle = calendar_name.strip().lower()
    if not needle:
        return "primary"

    matches = []
    for item in _all_calendar_list_items(service):
        summary = str(item.get("summary") or "").lower()
        if needle == summary or needle in summary:
            matches.append(item)

    if not matches:
        raise ValueError(f"no calendar found matching '{calendar_name}'")

    if len(matches) > 1:
        candidate_names = [str(item.get("summary") or "") for item in matches[:5]]
        raise ValueError(
            "multiple calendars matched calendar_name; use calendar_id. Matches: "
            + ", ".join(candidate_names)
        )

    matched_id = matches[0].get("id")
    if not matched_id:
        raise RuntimeError("matched calendar did not contain an id")

    return str(matched_id)


def _list_events_for_range(
    service,
    calendar_id: str,
    time_min: str,
    time_max: str,
    limit: int,
) -> list[dict[str, object]]:
    if limit <= 0:
        raise ValueError("limit must be greater than 0")

    max_results = min(limit, 2500)
    events: list[dict[str, object]] = []
    page_token: str | None = None

    while len(events) < limit:
        response = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=max_results,
                pageToken=page_token,
            )
            .execute()
        )

        items = response.get("items", [])
        events.extend(items)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return events[:limit]


def _format_event(event: dict[str, object]) -> dict[str, object]:
    start = event.get("start") or {}
    end = event.get("end") or {}
    organizer = event.get("organizer") or {}

    return {
        "id": event.get("id"),
        "summary": event.get("summary"),
        "description": event.get("description"),
        "location": event.get("location"),
        "status": event.get("status"),
        "html_link": event.get("htmlLink"),
        "start": {
            "date_time": start.get("dateTime"),
            "date": start.get("date"),
            "time_zone": start.get("timeZone"),
        },
        "end": {
            "date_time": end.get("dateTime"),
            "date": end.get("date"),
            "time_zone": end.get("timeZone"),
        },
        "organizer": {
            "email": organizer.get("email"),
            "display_name": organizer.get("displayName"),
        },
    }


def _resolve_event_window(
    time_window: Literal["day", "week", "custom"],
    target_date: str | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[date, date]:
    if time_window == "day":
        if not target_date:
            raise ValueError("date is required when time_window is 'day'")
        day_value = date.fromisoformat(target_date)
        return day_value, day_value

    if time_window == "week":
        if not target_date:
            raise ValueError("date is required when time_window is 'week'")
        day_value = date.fromisoformat(target_date)
        start_dt, end_dt = week_window_utc(day_value)
        return start_dt.date(), (end_dt.date() - timedelta(days=1))

    if time_window == "custom":
        if not start_date or not end_date:
            raise ValueError(
                "start_date and end_date are required when time_window is 'custom'"
            )
        start_day = date.fromisoformat(start_date)
        end_day = date.fromisoformat(end_date)
        if end_day < start_day:
            raise ValueError("end_date must be on or after start_date")
        return start_day, end_day

    raise ValueError("time_window must be one of: day, week, custom")


def register_google_calendar_tools(mcp) -> None:
    @mcp.tool
    def google_calendar_list_calendars() -> list[dict[str, object]]:
        """
        Returns all calendars available to the authenticated user.
        """
        service = _calendar_service()
        calendars = _all_calendar_list_items(service)
        calendars.sort(key=lambda item: str(item.get("summary") or "").lower())

        return [
            {
                "id": item.get("id"),
                "summary": item.get("summary"),
                "description": item.get("description"),
                "primary": item.get("primary", False),
                "time_zone": item.get("timeZone"),
                "access_role": item.get("accessRole"),
            }
            for item in calendars
        ]


    @mcp.tool
    def google_calendar_get_events(
        time_window: Literal["day", "week", "custom"] = "day",
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        calendar_id: str | None = None,
        calendar_name: str | None = None,
        limit: int = GOOGLE_CALENDAR_DEFAULT_LIMIT,
    ) -> dict[str, object]:
        """
        Returns Google Calendar events by time window.

        - time_window='day': events on date (YYYY-MM-DD)
        - time_window='week': events in the week containing date (YYYY-MM-DD)
        - time_window='custom': events from start_date through end_date (YYYY-MM-DD)

        Use calendar_id or calendar_name to query a specific calendar.
        """
        range_start_day, range_end_day = _resolve_event_window(
            time_window=time_window,
            target_date=date,
            start_date=start_date,
            end_date=end_date,
        )
        start_dt, _ = day_window_utc(range_start_day)
        _, end_dt = day_window_utc(range_end_day)

        service = _calendar_service()
        resolved_calendar_id = _resolve_calendar_id(service, calendar_id, calendar_name)

        events = _list_events_for_range(
            service=service,
            calendar_id=resolved_calendar_id,
            time_min=format_iso_utc(start_dt),
            time_max=format_iso_utc(end_dt),
            limit=limit,
        )

        return {
            "calendar_id": resolved_calendar_id,
            "time_window": time_window,
            "start_date": range_start_day.isoformat(),
            "end_date": range_end_day.isoformat(),
            "count": len(events),
            "events": [_format_event(event) for event in events],
        }
