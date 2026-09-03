from app.middleware.rate_limit import _endpoint_limit
from app.core.config import settings


def test_specific_endpoint_override_used():
    assert _endpoint_limit("/api/v1/uploads/presign") == settings.endpoint_rate_limits["/uploads/presign"]


def test_unmatched_endpoint_falls_back_to_default():
    assert _endpoint_limit("/api/v1/credits/balance") == settings.rate_limit_per_minute
