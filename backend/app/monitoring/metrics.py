"""Prometheus metrics. Import `metrics` and call `.labels(...).inc()` /
`.observe()` from services and jobs at the moment something happens —
metrics live next to the business logic that produces them, not bolted on
after the fact in main.py."""
from prometheus_client import Counter, Histogram

http_requests_total = Counter("vivid_http_requests_total", "HTTP requests", ["method", "path", "status"])
http_request_duration_seconds = Histogram("vivid_http_request_duration_seconds", "HTTP request latency", ["method", "path"])

generation_success_total = Counter("vivid_generation_success_total", "Successful generations", ["type", "model"])
generation_failure_total = Counter("vivid_generation_failure_total", "Failed generations", ["type", "model", "error_code"])
generation_duration_seconds = Histogram("vivid_generation_duration_seconds", "Time from submit to completion", ["type"])

provider_request_duration_seconds = Histogram("vivid_provider_request_duration_seconds", "Provider submit latency", ["provider"])

webhook_received_total = Counter("vivid_webhook_received_total", "Inbound webhooks", ["provider"])
webhook_failed_total = Counter("vivid_webhook_failed_total", "Webhooks that failed verification or processing", ["provider", "reason"])

rate_limit_redis_errors_total = Counter("vivid_rate_limit_redis_errors_total", "Redis errors encountered while rate limiting", ["endpoint"])
cache_errors_total = Counter("vivid_cache_errors_total", "Redis errors encountered while reading/writing the cache", ["operation"])

credits_reserved_total = Counter("vivid_credits_reserved_total", "Credits reserved")
credits_charged_total = Counter("vivid_credits_charged_total", "Credits actually charged")
credits_refunded_total = Counter("vivid_credits_refunded_total", "Credits refunded")

provider_cost_usd_total = Counter("vivid_provider_cost_usd_total", "Cumulative provider spend in USD", ["provider", "model"])
revenue_credits_total = Counter("vivid_revenue_credits_total", "Cumulative credits charged to users")

media_search_total = Counter("vivid_media_search_total", "Stock media searches", ["provider", "kind", "outcome"])
media_import_total = Counter("vivid_media_import_total", "Imported stock media assets", ["provider", "kind", "outcome"])
source_extraction_total = Counter("vivid_source_extraction_total", "URL/PPTX source extraction outcomes", ["source_type", "outcome"])
entitlement_block_total = Counter("vivid_entitlement_block_total", "Requests blocked by plan entitlements", ["plan", "reason"])
credit_purchase_total = Counter("vivid_credit_purchase_total", "Polar credit-pack purchase webhook grants", ["outcome"])
