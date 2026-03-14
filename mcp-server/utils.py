from datetime import date, datetime, timedelta, timezone


def parse_iso_datetime(value: str) -> datetime:
    # Canvas typically returns timestamps in UTC with a trailing Z.
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


def format_iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_link_header(link_header: str | None) -> dict[str, str]:
    if not link_header:
        return {}

    links: dict[str, str] = {}
    for part in link_header.split(","):
        section = part.strip().split(";")
        if len(section) < 2:
            continue

        url = section[0].strip()
        if not (url.startswith("<") and url.endswith(">")):
            continue

        rel = None
        for attr in section[1:]:
            item = attr.strip()
            if item.startswith("rel="):
                rel = item.split("=", 1)[1].strip('"')
                break

        if rel:
            links[rel] = url[1:-1]

    return links


def week_window_utc(reference_day: date) -> tuple[datetime, datetime]:
    week_start = reference_day - timedelta(days=reference_day.weekday())
    start_dt = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=7)
    return start_dt, end_dt


def day_window_utc(target_day: date) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(target_day, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=1)
    return start_dt, end_dt
