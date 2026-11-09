from datetime import datetime, timezone
from decimal import Decimal

from app.routers.account import _json_value


def test_account_export_serializes_database_values_without_changing_strings():
    moment = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert _json_value(moment) == "2026-01-02T03:04:05+00:00"
    assert _json_value(Decimal("1.2300")) == "1.2300"
    assert _json_value("uploads/user/private.mp4") == "uploads/user/private.mp4"
