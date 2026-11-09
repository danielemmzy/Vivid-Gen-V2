"""gap-closure (0006): SSRF-safe URL fetching, extracted from
workflows/url_to_video.py so it has exactly one implementation. Before
this, the only SSRF-protected fetch path in the codebase was private to
url_to_video.py — the new stock-asset URL fetch (orchestration/
asset_fetch.py, backing ScenePlan.stock_source_url) needed the same
protection, and duplicating it would have meant two independently-
maintained SSRF guards that could silently drift apart. Behavior is
unchanged from the original — see `_assert_public_host`'s docstring for
the one disclosed, unfixed limitation (DNS-rebinding TOCTOU)."""
import ipaddress
import socket
import urllib.robotparser
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.exceptions import VividGenError


class UrlFetchError(VividGenError):
    http_status = 422
    code = "URL_FETCH_FAILED"


class RobotsDisallowedError(VividGenError):
    http_status = 422
    code = "ROBOTS_DISALLOWED"


class SsrfBlockedError(VividGenError):
    http_status = 422
    code = "URL_NOT_ALLOWED"


_MAX_REDIRECTS = 5


def assert_public_host(hostname: str) -> None:
    """Resolves the hostname and rejects it if ANY resolved address is
    private, loopback, link-local (this also covers the cloud metadata
    endpoint 169.254.169.254), reserved, or multicast.

    Honest limitation, not hidden: this checks at resolution time, not at
    TCP-connect time, so a narrow DNS-rebinding attack (the name resolves
    to a public IP here, then to a private one microseconds later when
    httpx actually connects) is not fully closed. Fully closing that needs
    a custom transport that connects to the exact IP already validated,
    not a second lookup — real hardening, not done in this pass."""
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UrlFetchError("Could not resolve this URL's hostname", details={"hostname": hostname, "cause": str(exc)}) from exc

    for info in addr_infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise SsrfBlockedError(
                "This URL resolves to a private or reserved network address and can't be fetched",
                details={"hostname": hostname},
            )


def assert_fetchable(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SsrfBlockedError("Only http/https URLs are allowed", details={"url": url})
    if not parsed.hostname:
        raise UrlFetchError("This doesn't look like a valid URL", details={"url": url})
    assert_public_host(parsed.hostname)
    return parsed.hostname


async def check_robots_txt(url: str) -> None:
    if not settings.respect_robots_txt:
        return
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = urllib.robotparser.RobotFileParser()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(robots_url)
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
            else:
                return  # no robots.txt, or unreachable — treat as allowed
    except httpx.HTTPError:
        return  # fail open on robots.txt fetch errors — don't block on infra flakiness
    if not parser.can_fetch("VividGenBot", url):
        raise RobotsDisallowedError("This URL's robots.txt disallows automated access", details={"url": url})


async def fetch_with_validated_redirects(url: str, *, stream: bool = False) -> httpx.Response:
    """Follows redirects manually (httpx's own follow_redirects=True would
    fetch every hop without re-checking it) so each hop gets the same
    scheme+host validation as the original URL — a malicious or
    compromised site redirecting to an internal address is exactly the
    other half of the SSRF surface, not just the URL the user typed.

    `stream=True` returns a response opened for streaming (caller must
    read `.aiter_bytes()` and close it) — used by `download_url_to_path`
    for binary media where buffering the whole body in memory first would
    defeat `url_fetch_max_bytes`."""
    current_url = url
    client = httpx.AsyncClient(timeout=settings.url_fetch_timeout_seconds, follow_redirects=False)
    try:
        for _ in range(_MAX_REDIRECTS):
            assert_fetchable(current_url)
            headers = {"User-Agent": "VividGenBot/1.0 (+content extraction for video generation)"}
            try:
                if stream:
                    request = client.build_request("GET", current_url, headers=headers)
                    response = await client.send(request, stream=True)
                else:
                    response = await client.get(current_url, headers=headers)
            except httpx.HTTPError as exc:
                raise UrlFetchError("Could not fetch this URL", details={"url": current_url, "cause": str(exc)}) from exc
            if response.is_redirect:
                next_url = response.headers.get("location")
                await response.aclose()
                if not next_url:
                    raise UrlFetchError("Redirect with no location header", details={"url": current_url})
                current_url = httpx.URL(current_url).join(next_url).human_repr()
                continue
            response.raise_for_status()
            if not stream:
                await client.aclose()
            return response
    except Exception:
        await client.aclose()
        raise
    await client.aclose()
    raise UrlFetchError("Too many redirects", details={"url": url})


async def download_url_to_path(url: str, dest_path: str, *, max_bytes: int | None = None) -> str:
    """Streams a URL to a local file, enforcing the same size cap as
    `extract_article_text` (or an explicit `max_bytes`), aborting mid-
    download rather than buffering an oversized response first. Returns
    the response's content-type for the caller to validate against an
    expected media kind (e.g. "image/*" or "video/*")."""
    limit = max_bytes or settings.url_fetch_max_bytes
    response = await fetch_with_validated_redirects(url, stream=True)
    try:
        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        total = 0
        with open(dest_path, "wb") as f:
            async for chunk in response.aiter_bytes(chunk_size=65536):
                total += len(chunk)
                if total > limit:
                    raise UrlFetchError("Downloaded file exceeds the size limit", details={"url": url, "limit_bytes": limit})
                f.write(chunk)
        return content_type
    finally:
        await response.aclose()
