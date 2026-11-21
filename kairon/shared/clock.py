from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current UTC time as a naive datetime.

    MongoEngine fields and existing comparisons store naive UTC values.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def utc_from_timestamp(timestamp: float) -> datetime:
    """Return a naive UTC datetime for a POSIX timestamp.

    Matches datetime.utcfromtimestamp so stored values and comparisons stay naive.
    """
    return datetime.fromtimestamp(timestamp, UTC).replace(tzinfo=None)
