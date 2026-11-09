"""S3 presigned URL issuance, with an optional CloudFront signed-URL path
for downloads. The architecture review correctly flagged that
`cdn_base_url` existed in settings but the signing path was an unfilled
`pass` — this implements it for real: when CLOUDFRONT_KEY_PAIR_ID and
CLOUDFRONT_PRIVATE_KEY_PATH are set, downloads are signed CloudFront URLs
served from a private S3 origin (never a public-read bucket); otherwise it
falls back to a direct S3 presigned URL, which is what every environment
without a CDN provisioned yet (local dev, early staging) should use."""
from datetime import datetime, timedelta
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.signers import CloudFrontSigner

from app.core.exceptions import VividGenError

from app.core.config import settings

_client = boto3.client(
    "s3", region_name=settings.aws_region, aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key, config=Config(signature_version="s3v4"),
)

_cloudfront_signer: CloudFrontSigner | None = None


def _rsa_signer(message: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    with open(settings.cloudfront_private_key_path, "rb") as key_file:  # type: ignore[arg-type]
        private_key = serialization.load_pem_private_key(key_file.read(), password=None)
    return private_key.sign(message, padding.PKCS1v15(), hashes.SHA1())  # noqa: S303 - CloudFront requires SHA1 for this signature


def _get_cloudfront_signer() -> CloudFrontSigner:
    global _cloudfront_signer
    if _cloudfront_signer is None:
        _cloudfront_signer = CloudFrontSigner(settings.cloudfront_key_pair_id, _rsa_signer)
    return _cloudfront_signer


def presign_upload(content_type: str, extension: str, purpose: str) -> tuple[str, str]:
    safe_ext = extension.strip(".").lower()[:10]
    key = f"{settings.s3_input_prefix}/{purpose}/{uuid4().hex}.{safe_ext}"
    url = _client.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.aws_s3_bucket_name, "Key": key, "ContentType": content_type},
        ExpiresIn=settings.s3_presigned_ttl_seconds,
    )
    return url, key


def presign_download(key: str, expires: int = 900) -> str:
    if settings.cdn_base_url and settings.cloudfront_key_pair_id and settings.cloudfront_private_key_path:
        url = f"{settings.cdn_base_url.rstrip('/')}/{key}"
        expire_at = datetime.utcnow() + timedelta(seconds=expires)
        return _get_cloudfront_signer().generate_presigned_url(url, date_less_than=expire_at)
    # No CDN provisioned yet — fall back to a direct, still-private S3
    # presigned URL. This is a legitimate steady state for local dev/early
    # staging, not a broken CDN; see the architecture plan's Phase 10 for
    # when to provision CloudFront in front of the (still-private) bucket.
    return _client.generate_presigned_url(
        "get_object", Params={"Bucket": settings.aws_s3_bucket_name, "Key": key}, ExpiresIn=expires
    )


def object_exists(key: str) -> bool:
    try:
        _client.head_object(Bucket=settings.aws_s3_bucket_name, Key=key)
        return True
    except Exception:  # noqa: BLE001 - boto3 raises a botocore ClientError subclass
        return False


def upload_bytes(key: str, data: bytes, content_type: str) -> None:
    _client.put_object(Bucket=settings.aws_s3_bucket_name, Key=key, Body=data, ContentType=content_type)


class DownloadTooLargeError(VividGenError):
    """Raised by download_to_path when the object exceeds
    settings.max_upload_bytes — see that function's docstring for why
    this check lives here rather than at upload time."""
    http_status = 413
    code = "FILE_TOO_LARGE"


def download_to_path(key: str, local_path: str) -> None:
    """`max_upload_bytes` was declared in settings but never actually
    enforced anywhere (a real gap — presigned PUT URLs have no built-in
    server-side size limit unless you switch to presigned POST with
    policy conditions, which is a bigger change than this pass makes).
    This is the pragmatic fix: check the object's real size via S3's own
    metadata before pulling it, so an oversized file gets rejected here —
    the one place every workflow that processes an uploaded/referenced
    file already goes through — rather than silently processing
    something arbitrarily large."""
    head = _client.head_object(Bucket=settings.aws_s3_bucket_name, Key=key)
    size = head.get("ContentLength", 0)
    if size > settings.max_upload_bytes:
        raise DownloadTooLargeError(
            f"This file is too large to process ({size} bytes, limit is {settings.max_upload_bytes})",
            details={"key": key, "size": size, "limit": settings.max_upload_bytes},
        )
    _client.download_file(settings.aws_s3_bucket_name, key, local_path)


def upload_from_path(local_path: str, key: str, content_type: str) -> None:
    _client.upload_file(local_path, settings.aws_s3_bucket_name, key, ExtraArgs={"ContentType": content_type})


def delete_object(key: str) -> None:
    """Delete only V2-owned input/output objects.

    The caller still needs the narrow ``s3:DeleteObject`` permission. An
    AccessDenied response is intentionally propagated so cleanup cannot report
    success while leaving an orphan behind.
    """
    allowed_prefixes = (
        f"{settings.s3_input_prefix}/",
        f"{settings.s3_output_prefix}/",
    )
    if not key.startswith(allowed_prefixes):
        raise VividGenError("Object key is outside the V2 storage prefixes", details={"key": key})
    _client.delete_object(Bucket=settings.aws_s3_bucket_name, Key=key)
