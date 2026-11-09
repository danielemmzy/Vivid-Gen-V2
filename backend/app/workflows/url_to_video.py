"""URL -> video: SSRF-safe article text + representative visual extraction."""
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from pydantic import BaseModel, Field
from bs4 import BeautifulSoup
from app.core.safe_fetch import UrlFetchError, assert_fetchable, check_robots_txt, fetch_with_validated_redirects
from app.core.config import settings
from app.workflows.visual_extraction import import_public_image


class UrlToVideoRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    duration_seconds: int = Field(default=60, ge=15, le=300)
    style: str | None = None
    language: str = "en"
    article_text: str | None = Field(default=None, min_length=1, max_length=15000)


class UrlToVideoPreviewRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


@dataclass(frozen=True)
class ArticleSource:
    title: str | None
    description: str | None
    text: str
    visual_urls: list[str]


async def _extract_article_source(url: str) -> ArticleSource:
    """Fetch an article once without importing assets, for source review."""
    assert_fetchable(url)
    await check_robots_txt(url)
    response = await fetch_with_validated_redirects(url)
    if len(response.content) > settings.url_fetch_max_bytes:
        raise UrlFetchError("Page exceeds the size limit for extraction", details={"url": url})
    content_type = response.headers.get("content-type", "").lower()
    if content_type and "html" not in content_type and "xhtml" not in content_type:
        raise UrlFetchError("This URL did not return an HTML article page", details={"url": url, "content_type": content_type})

    soup = BeautifulSoup(response.text, "html.parser")
    title_node = soup.find("meta", {"property": "og:title"}) or soup.find("title")
    title = title_node.get("content") if title_node and title_node.name == "meta" else title_node.get_text(" ", strip=True) if title_node else None
    description_node = soup.find("meta", {"name": "description"}) or soup.find("meta", {"property": "og:description"})
    description = description_node.get("content", "").strip() if description_node else None
    visual_urls: list[str] = []
    for selector in (("meta", {"property": "og:image"}), ("meta", {"name": "twitter:image"})):
        for node in soup.find_all(*selector):
            raw = node.get("content")
            if raw:
                visual_urls.append(urljoin(url, raw.strip()))
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()
    container = soup.find("article") or soup.find("main") or soup.body or soup
    for img in container.find_all("img"):
        raw = img.get("src") or img.get("data-src") or img.get("data-original")
        if not raw and img.get("srcset"):
            raw = img.get("srcset").split(",")[-1].strip().split(" ")[0]
        if not raw:
            continue
        width = int(img.get("width", 0)) if str(img.get("width", "0")).isdigit() else 0
        height = int(img.get("height", 0)) if str(img.get("height", "0")).isdigit() else 0
        if (width and width < 160) or (height and height < 100):
            continue
        visual_urls.append(urljoin(url, raw.strip()))
    text = " ".join(container.get_text(separator=" ").split())
    if not text:
        raise UrlFetchError("No extractable article text found at this URL", details={"url": url})
    unique: list[str] = []
    for image_url in visual_urls:
        parsed = urlparse(image_url)
        if parsed.scheme in ("http", "https") and parsed.hostname and image_url not in unique:
            unique.append(image_url)
        if len(unique) >= max(settings.url_reference_max_images * 4, 8):
            break
    return ArticleSource(title=title, description=description, text=text[:15000], visual_urls=unique)


async def preview_article(url: str) -> dict:
    source = await _extract_article_source(url)
    return {
        "url": url,
        "title": source.title,
        "description": source.description,
        "article_text": source.text,
        "word_count": len(source.text.split()),
        "visual_candidates": len(source.visual_urls),
    }


async def extract_article(url: str, *, user_id: str | None = None) -> tuple[str, list[str], list[str]]:
    source = await _extract_article_source(url)
    imported: list[str] = []
    visual_notes: list[str] = []
    if user_id:
        for image_url in source.visual_urls:
            result = await import_public_image(image_url, user_id=user_id, purpose="url-reference")
            if result:
                imported.append(result[0])
                visual_notes.append(f"Article visual successfully imported as a private image reference from {urlparse(image_url).hostname}.")
            if len(imported) >= settings.url_reference_max_images:
                break
    else:
        # Text-only callers may inspect candidate availability, but they never receive private reference keys.
        visual_notes = [f"Article image candidate found on {urlparse(u).hostname}; not imported in this text-only extraction." for u in source.visual_urls[:settings.url_reference_max_images]]
    return source.text, imported, visual_notes


async def extract_article_text(url: str) -> str:
    text, _, _ = await extract_article(url)
    return text


async def build_plan_inputs(body: UrlToVideoRequest, user_id: str | None = None) -> dict:
    article_text, reference_keys, visual_notes = await extract_article(body.url, user_id=user_id)
    source_facts = body.article_text.strip() if body.article_text else article_text
    if visual_notes:
        source_facts += "\n\nVISUAL REFERENCES FOUND (use only as grounded visual guidance):\n" + "\n".join(visual_notes)
    return {
        "prompt": f"Create a {body.duration_seconds}-second video summarizing this article for social media.",
        "project_type": "video",
        "duration_seconds": body.duration_seconds,
        "style": body.style,
        "language": body.language,
        "source_facts": source_facts,
        "reference_image_s3_keys": reference_keys,
        "source_url": body.url,
    }
