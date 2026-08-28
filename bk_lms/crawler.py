from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import re
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_markdown
from playwright.async_api import APIResponse, BrowserContext, Page, async_playwright


LMS_BASE = "https://lms.hcmut.edu.vn"
DEFAULT_PROFILE_DIR = Path(".bk-lms-profile")

# Content-bearing Moodle routes. Deliberately excludes global navigation and
# forum discussion pages (which may contain classmates' personal content).
FOLLOW_MODS = {
    "assign",
    "book",
    "folder",
    "lesson",
    "page",
    "quiz",
    "resource",
    "url",
    "wiki",
}
FOLLOW_PATH_RE = re.compile(
    r"^/mod/(?:" + "|".join(sorted(FOLLOW_MODS)) + r")/view\.php$"
)
FILE_EXTENSIONS = {
    ".7z", ".csv", ".doc", ".docx", ".epub", ".gif", ".jpeg", ".jpg",
    ".json", ".md", ".mp3", ".mp4", ".odp", ".ods", ".odt", ".pdf",
    ".png", ".ppt", ".pptx", ".rar", ".rtf", ".svg", ".txt", ".webm",
    ".webp", ".xls", ".xlsx", ".xml", ".zip",
}


@dataclass(slots=True)
class LinkSeed:
    url: str
    title: str
    section: str
    item_type: str
    relation: str = "activity"


@dataclass(slots=True)
class Record:
    kind: str
    url: str
    title: str = ""
    section: str = ""
    item_type: str = ""
    relation: str = ""
    local_path: str | None = None
    content_type: str | None = None
    sha256: str | None = None
    note: str | None = None


@dataclass(slots=True)
class CourseActivity:
    title: str
    section: str
    item_type: str
    url: str | None
    inline_text: str = ""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def course_id_from_url(url: str) -> str:
    values = parse_qs(urlparse(url).query).get("id", [])
    if not values or not values[0].isdigit():
        raise ValueError(f"Course URL must contain a numeric id=: {url}")
    return values[0]


def sanitize_filename(value: str, fallback: str = "item") -> str:
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", value).strip(" .")
    value = re.sub(r"\s+", " ", value)
    return (value[:160] or fallback).strip()


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    # Fragments do not affect server content and create needless duplicates.
    return parsed._replace(fragment="").geturl()


def is_lms_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc == "lms.hcmut.edu.vn"


def should_follow_html(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc != "lms.hcmut.edu.vn":
        return False
    if FOLLOW_PATH_RE.match(parsed.path):
        return True
    return False


def looks_like_file_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc != "lms.hcmut.edu.vn":
        return False
    if parsed.path.startswith("/pluginfile.php/"):
        return True
    return Path(parsed.path).suffix.lower() in FILE_EXTENSIONS


def activity_type(classes: Iterable[str]) -> str:
    for class_name in classes:
        if class_name.startswith("modtype_"):
            return class_name.removeprefix("modtype_")
    return "unknown"


def main_region(soup: BeautifulSoup):
    return (
        soup.select_one("#region-main")
        or soup.select_one('[role="main"]')
        or soup.select_one("main")
        or soup.body
        or soup
    )


def normalized_text(node) -> str:
    return " ".join(node.stripped_strings)


def parse_course_page(html: str) -> tuple[str, list[CourseActivity]]:
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one("h1") or soup.select_one("title")
    title = normalized_text(title_node) if title_node else "BK-LMS course"
    if title.startswith("Course:"):
        title = title.removeprefix("Course:").strip()
    if "|" in title:
        title = title.split("|", 1)[0].strip()

    activities: list[CourseActivity] = []
    sections = soup.select('li.section[data-for="section"], li.course-section, section.course-section')
    if not sections:
        sections = [main_region(soup)]

    for section in sections:
        section_title_node = section.select_one(
            "h3.sectionname, h3.section-name, .sectionname, [data-for='section_title']"
        )
        section_title = normalized_text(section_title_node) if section_title_node else "General"
        activity_nodes = section.select('li.activity[data-for="cmitem"], li.activity')
        seen_nodes: set[str] = set()
        for activity in activity_nodes:
            key = activity.get("data-id") or activity.get("id") or str(id(activity))
            if key in seen_nodes:
                continue
            seen_nodes.add(key)

            classes = activity.get("class", [])
            item_type = activity_type(classes)

            link = activity.select_one(".activityname a[href], a.aalink[href], a[href]")
            url = urljoin(LMS_BASE, link["href"]) if link and link.get("href") else None
            title_node = activity.select_one(".instancename, [data-activityname]")
            item_title = (
                normalized_text(title_node)
                if title_node
                else (normalized_text(link) if link else normalized_text(activity))
            )
            item_title = re.sub(
                rf"\s+(?:{re.escape(item_type)}|assignment|file|url|page|quiz|folder)$",
                "",
                item_title,
                flags=re.IGNORECASE,
            ).strip()
            if not item_title:
                item_title = f"Untitled {item_type}"

            inline_text = normalized_text(activity) if url is None else ""
            activities.append(
                CourseActivity(
                    title=item_title,
                    section=section_title,
                    item_type=item_type,
                    url=canonical_url(url) if url else None,
                    inline_text=inline_text,
                )
            )
    return title, activities


def content_disposition_filename(value: str | None) -> str | None:
    if not value:
        return None
    utf8 = re.search(r"filename\*=UTF-8''([^;]+)", value, flags=re.IGNORECASE)
    if utf8:
        from urllib.parse import unquote
        return unquote(utf8.group(1))
    plain = re.search(r'filename="?([^";]+)"?', value, flags=re.IGNORECASE)
    return plain.group(1).strip() if plain else None


def extension_for_content_type(content_type: str) -> str:
    mime = content_type.split(";", 1)[0].strip()
    return mimetypes.guess_extension(mime) or ""


class CourseCrawler:
    def __init__(
        self,
        course_url: str,
        output_dir: Path,
        profile_dir: Path = DEFAULT_PROFILE_DIR,
        *,
        headless: bool = False,
        max_pages: int = 200,
    ) -> None:
        self.course_url = canonical_url(course_url)
        self.course_id = course_id_from_url(course_url)
        self.output_dir = output_dir
        self.profile_dir = profile_dir
        self.headless = headless
        self.max_pages = max_pages
        self.records: list[Record] = []
        self.context: BrowserContext | None = None

    async def run(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "pages").mkdir(exist_ok=True)
        (self.output_dir / "files").mkdir(exist_ok=True)
        (self.output_dir / "raw").mkdir(exist_ok=True)

        async with async_playwright() as p:
            self.context = await p.chromium.launch_persistent_context(
                str(self.profile_dir),
                headless=self.headless,
                accept_downloads=False,
            )
            page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            await self._open_authenticated_course(page)

            html = await page.content()
            (self.output_dir / "raw" / "course.html").write_text(html, encoding="utf-8")
            course_title, activities = parse_course_page(html)

            queue: deque[LinkSeed] = deque()
            for item in activities:
                if item.url:
                    queue.append(
                        LinkSeed(
                            url=item.url,
                            title=item.title,
                            section=item.section,
                            item_type=item.item_type,
                        )
                    )
                else:
                    self.records.append(
                        Record(
                            kind="inline",
                            url=f"{self.course_url}#inline",
                            title=item.title,
                            section=item.section,
                            item_type=item.item_type,
                            relation="activity",
                            note=item.inline_text,
                        )
                    )

            await self._crawl_queue(queue)
            self._write_manifest()
            self._write_index(course_title, activities)
            await self.context.close()

        return self.output_dir / "index.md"

    async def _open_authenticated_course(self, page: Page) -> None:
        await page.goto(self.course_url, wait_until="domcontentloaded")
        if self._is_course_page(page.url):
            return
        if self.headless:
            raise RuntimeError(
                "BK-LMS session is not authenticated. Run once without --headless, "
                "log in in the opened browser, then rerun."
            )

        print("\nBK-LMS needs authentication.")
        print("Log in in the opened browser window. Do not paste your password into the terminal.")
        await asyncio.to_thread(input, "After login is complete, press Enter here...")
        await page.goto(self.course_url, wait_until="domcontentloaded")
        if not self._is_course_page(page.url):
            raise RuntimeError(
                f"Could not reach the course after login. Current URL: {page.url}"
            )

    def _is_course_page(self, url: str) -> bool:
        parsed = urlparse(url)
        return (
            parsed.netloc == "lms.hcmut.edu.vn"
            and parsed.path == "/course/view.php"
            and parse_qs(parsed.query).get("id", [None])[0] == self.course_id
        )

    async def _crawl_queue(self, queue: deque[LinkSeed]) -> None:
        seen: set[str] = set()
        while queue and len(seen) < self.max_pages:
            seed = queue.popleft()
            url = canonical_url(seed.url)
            if url in seen:
                continue
            seen.add(url)

            if not is_lms_url(url):
                self.records.append(
                    Record(
                        kind="external",
                        url=url,
                        title=seed.title,
                        section=seed.section,
                        item_type=seed.item_type,
                        relation=seed.relation,
                    )
                )
                continue

            response, final_url, external_redirect = await self._fetch_internal(url)
            if external_redirect:
                self.records.append(
                    Record(
                        kind="external",
                        url=external_redirect,
                        title=seed.title,
                        section=seed.section,
                        item_type=seed.item_type,
                        relation=seed.relation,
                        note=f"Redirected from {url}",
                    )
                )
                continue
            if response is None:
                self.records.append(
                    Record(
                        kind="error",
                        url=url,
                        title=seed.title,
                        section=seed.section,
                        item_type=seed.item_type,
                        relation=seed.relation,
                        note="Request failed",
                    )
                )
                continue

            content_type = response.headers.get("content-type", "").lower()
            body = await response.body()
            if "text/html" in content_type or "application/xhtml+xml" in content_type:
                record, discovered = self._save_html(
                    final_url, body, seed, content_type
                )
                self.records.append(record)
                queue.extend(discovered)
            else:
                self.records.append(
                    self._save_file(final_url, body, seed, response)
                )

    async def _fetch_internal(
        self, url: str
    ) -> tuple[APIResponse | None, str, str | None]:
        assert self.context is not None
        current = url
        for _ in range(10):
            try:
                response = await self.context.request.get(
                    current,
                    max_redirects=0,
                    timeout=30_000,
                    fail_on_status_code=False,
                )
            except Exception:
                return None, current, None

            if 300 <= response.status < 400:
                location = response.headers.get("location")
                if not location:
                    return response, current, None
                target = canonical_url(urljoin(current, location))
                if not is_lms_url(target):
                    return None, current, target
                current = target
                continue
            return response, canonical_url(response.url or current), None
        return None, current, None

    def _save_html(
        self,
        url: str,
        body: bytes,
        seed: LinkSeed,
        content_type: str,
    ) -> tuple[Record, list[LinkSeed]]:
        html = body.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        region = main_region(soup)
        for selector in (
            "nav",
            ".secondary-navigation",
            ".drawer",
            ".block",
            ".breadcrumb",
            ".activity-navigation",
            "form[action*='logout']",
        ):
            for node in region.select(selector):
                node.decompose()

        page_title_node = region.select_one("h1, h2") or soup.select_one("title")
        page_title = normalized_text(page_title_node) if page_title_node else seed.title
        markdown = html_to_markdown(str(region), heading_style="ATX").strip()
        digest = hashlib.sha256(body).hexdigest()
        filename = sanitize_filename(seed.title or page_title)
        rel_path = Path("pages") / f"{filename}-{digest[:8]}.md"
        full_path = self.output_dir / rel_path
        full_path.write_text(
            "\n".join(
                [
                    f"# {page_title or seed.title}",
                    "",
                    f"Source: {url}",
                    "",
                    markdown,
                    "",
                ]
            ),
            encoding="utf-8",
        )

        discovered: list[LinkSeed] = []
        for link in region.select("a[href]"):
            href = link.get("href")
            if not href:
                continue
            target = canonical_url(urljoin(url, href))
            link_title = normalized_text(link) or Path(urlparse(target).path).name or target
            if not is_lms_url(target):
                self.records.append(
                    Record(
                        kind="external",
                        url=target,
                        title=link_title,
                        section=seed.section,
                        item_type=seed.item_type,
                        relation="linked-from-page",
                        note=f"Found on {url}",
                    )
                )
            elif looks_like_file_url(target) or should_follow_html(target):
                discovered.append(
                    LinkSeed(
                        url=target,
                        title=link_title,
                        section=seed.section,
                        item_type=seed.item_type,
                        relation="linked-from-page",
                    )
                )

        return (
            Record(
                kind="page",
                url=url,
                title=page_title or seed.title,
                section=seed.section,
                item_type=seed.item_type,
                relation=seed.relation,
                local_path=rel_path.as_posix(),
                content_type=content_type,
                sha256=digest,
            ),
            discovered,
        )

    def _save_file(
        self,
        url: str,
        body: bytes,
        seed: LinkSeed,
        response: APIResponse,
    ) -> Record:
        content_type = response.headers.get("content-type", "application/octet-stream")
        disposition_name = content_disposition_filename(
            response.headers.get("content-disposition")
        )
        url_name = Path(urlparse(url).path).name
        name = disposition_name or url_name or seed.title
        name = sanitize_filename(name, fallback="resource")
        if "." not in Path(name).name:
            name += extension_for_content_type(content_type)

        digest = hashlib.sha256(body).hexdigest()
        rel_path = Path("files") / f"{digest[:8]}-{name}"
        (self.output_dir / rel_path).write_bytes(body)
        return Record(
            kind="file",
            url=url,
            title=seed.title or name,
            section=seed.section,
            item_type=seed.item_type,
            relation=seed.relation,
            local_path=rel_path.as_posix(),
            content_type=content_type,
            sha256=digest,
        )

    def _write_manifest(self) -> None:
        path = self.output_dir / "manifest.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            meta = {
                "kind": "crawl",
                "course_id": self.course_id,
                "course_url": self.course_url,
                "scraped_at": utc_now_iso(),
                "record_count": len(self.records),
            }
            fh.write(json.dumps(meta, ensure_ascii=False) + "\n")
            for record in self.records:
                fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def _write_index(
        self, course_title: str, activities: list[CourseActivity]
    ) -> None:
        local_by_url: dict[str, str] = {}
        for record in self.records:
            if record.local_path and record.url not in local_by_url:
                local_by_url[record.url] = record.local_path

        sections: dict[str, list[CourseActivity]] = {}
        for activity in activities:
            sections.setdefault(activity.section, []).append(activity)

        lines = [
            f"# {course_title}",
            "",
            f"- LMS course: {self.course_url}",
            f"- Course ID: `{self.course_id}`",
            f"- Exported: {utc_now_iso()}",
            "- Generated by BK-Scraper v0. This is a retrieval snapshot, not a sync engine.",
            "",
        ]
        for section, items in sections.items():
            lines.extend([f"## {section}", ""])
            for item in items:
                label = f"**{item.title}**"
                type_text = f"`{item.item_type}`"
                if item.url:
                    local = local_by_url.get(item.url)
                    if local:
                        lines.append(
                            f"- {label} {type_text} — [local]({local}) · [LMS]({item.url})"
                        )
                    else:
                        lines.append(f"- {label} {type_text} — [LMS]({item.url})")
                else:
                    text = item.inline_text.replace("\n", " ").strip()
                    lines.append(f"- {label} {type_text}" + (f" — {text}" if text else ""))
            lines.append("")

        lines.extend(
            [
                "## Files",
                "",
                "- Machine-readable crawl map: [manifest.jsonl](manifest.jsonl)",
                "- Original course landing page: [raw/course.html](raw/course.html)",
                "",
                "Interactive quiz attempts, submissions, and forum discussions are not mirrored by v0.",
                "",
            ]
        )
        (self.output_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def default_pkv_root() -> Path:
    env = os.environ.get("PKV_PATH")
    if env:
        return Path(env).expanduser()

    windows = Path(r"C:\Users\minhc\Code\Personal-Knowledge-Vault")
    if os.name == "nt" and windows.exists():
        return windows

    sibling = Path("../Personal-Knowledge-Vault")
    return sibling


async def crawl_course(
    course_url: str,
    *,
    pkv_root: Path | None = None,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    headless: bool = False,
    max_pages: int = 200,
) -> Path:
    course_id = course_id_from_url(course_url)
    root = (pkv_root or default_pkv_root()).expanduser()
    output_dir = root / "lms" / "courses" / course_id
    crawler = CourseCrawler(
        course_url,
        output_dir,
        profile_dir,
        headless=headless,
        max_pages=max_pages,
    )
    return await crawler.run()
