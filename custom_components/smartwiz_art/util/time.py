from datetime import timedelta


def format_duration(
    td: timedelta | int | float,
    *,
    compact: bool = True,
    include_seconds: bool = False,
) -> str:
    """
    Format duration into human-readable string.

    Args:
        td: timedelta or seconds
        compact: True -> "3h12m", False -> "3h 12m"
        include_seconds: include seconds component

    Examples:
        3h12m
        5m30s
        45s
    """
    if isinstance(td, timedelta):
        total_seconds = int(td.total_seconds())
    else:
        total_seconds = int(td)

    if total_seconds <= 0:
        return "0s"

    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)

    sep = "" if compact else " "

    parts = []

    if hours > 0:
        parts.append(f"{hours}h")

    if minutes > 0 or (hours > 0 and include_seconds):
        parts.append(f"{minutes:02d}m" if hours > 0 else f"{minutes}m")

    if include_seconds and (seconds > 0 or not parts):
        parts.append(f"{seconds:02d}s" if minutes > 0 or hours > 0 else f"{seconds}s")

    return sep.join(parts)
