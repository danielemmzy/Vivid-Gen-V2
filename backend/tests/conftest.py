"""Shared test env setup — every test module needs these settings present
before app.core.config is imported anywhere in the import chain."""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/vividgen_test")
os.environ.setdefault("BACKEND_PUBLIC_URL", "http://localhost:8000")
os.environ.setdefault("INTERNAL_API_SECRET", "x" * 64)
os.environ.setdefault("FAL_KEY", "test")
os.environ.setdefault("FAL_WEBHOOK_URL", "http://localhost:8000/api/v1/webhooks/fal")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_S3_BUCKET_NAME", "test")
