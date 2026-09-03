"""Chaos-testing Test 8 — load test, against GENERATION_PROVIDER=fake so
this costs nothing regardless of scale. Run with:

    GENERATION_PROVIDER=fake uvicorn app.main:app &   # or docker compose up
    locust -f loadtest/locustfile.py --host http://localhost:8000

Then drive it from the web UI (http://localhost:8089) through the stages
the audit asked for:
    100 users / 1,000 requests
    500 users / 5,000 requests
and watch Locust's own p50/p95/p99/error-rate charts alongside
GET /metrics on the API (vivid_http_request_duration_seconds,
vivid_generation_duration_seconds, DB pool exhaustion shows up as rising
latency on every endpoint at once, not just /generations).

Each simulated user has its own fake identity signed the same way the
real Next.js frontend signs requests — see backend/app/core/security.py.
"""
import hashlib
import hmac
import os
import random
import time

from locust import HttpUser, task, between

INTERNAL_API_SECRET = os.environ["INTERNAL_API_SECRET"]  # must match the running API's .env

with open(os.path.join(os.path.dirname(__file__), "seeded_users.txt")) as f:
    SEEDED_USER_IDS = [line.strip() for line in f if line.strip()]
if not SEEDED_USER_IDS:
    raise RuntimeError(
        "loadtest/seeded_users.txt is empty — run `python -m loadtest.seed_test_users` "
        "against your test database first, or every request 500s on 'user not found'."
    )

PROMPTS = [
    "a golden retriever running on a beach at sunset",
    "a neon-lit cyberpunk city street in the rain",
    "a watercolor painting of mountains at dawn",
    "a close-up of a steaming cup of coffee",
]


def _signed_headers(user_id: str) -> dict:
    timestamp = str(int(time.time()))
    role = "user"
    signature = hmac.new(INTERNAL_API_SECRET.encode(), f"{user_id}:{timestamp}:{role}".encode(), hashlib.sha256).hexdigest()
    return {
        "X-Vivid-User-ID": user_id,
        "X-Vivid-Timestamp": timestamp,
        "X-Vivid-Role": role,
        "X-Vivid-Signature": signature,
        "Content-Type": "application/json",
    }


class VividGenUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        # Draw from the pre-seeded pool (see seed_test_users.py) so every
        # simulated user maps to a real, credited account instead of a
        # fresh user_id the backend has never seen.
        self.user_id = random.choice(SEEDED_USER_IDS)

    @task(5)
    def submit_text_to_image(self):
        self.client.post(
            "/api/v1/generations/text-to-image",
            json={"prompt": random.choice(PROMPTS), "model": "seedream-v4", "num_images": 1},
            headers=_signed_headers(self.user_id),
            name="/generations/text-to-image",
        )

    @task(2)
    def list_generations(self):
        self.client.get(
            "/api/v1/generations?limit=20",
            headers=_signed_headers(self.user_id),
            name="/generations [list]",
        )

    @task(2)
    def check_balance(self):
        self.client.get(
            "/api/v1/credits/balance",
            headers=_signed_headers(self.user_id),
            name="/credits/balance",
        )

    @task(1)
    def list_models(self):
        self.client.get("/api/v1/models", headers=_signed_headers(self.user_id), name="/models")
