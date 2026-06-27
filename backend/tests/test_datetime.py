from datetime import datetime

from app.core.datetime import utcnow_iso


def test_utcnow_iso_has_explicit_utc_timezone():
    value = utcnow_iso()

    assert value.endswith("Z")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.utcoffset().total_seconds() == 0
