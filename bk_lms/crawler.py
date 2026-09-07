from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
from html import unescape as unescape_html
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_markdown
from playwright.async_api import APIResponse, BrowserContext, Page, async_playwright

from .auth import authenticate_page
from .browser import launch_persistent_lms_context, save_storage_state
from .policy import (
    FILE_EXTENSIONS,
    classify_url,
    looks_like_file_url as policy_looks_like_file_url,
    should_follow_html as policy_should_follow_html,
)


LMS_BASE = "https://lms.hcmut.edu.vn"
DEFAULT_PROFILE_DIR = Path(".bk-lms-profile")


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
    resolved_url: str | None = None
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


@dataclass(slots=True)
class AuditEvent:
    url: str
    decision: str
    reason: str
    title: str = ""
    item_type: str = ""
    kind: str = ""
    relation: str = ""


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
    return parsed._replace(fragment="").geturl()


def is_lms_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc == "lms.hcmut.edu.vn"


def should_follow_html(url: str, source_course_id: str = "") -> bool:
    return policy_should_follow_html(url, source_course_id)


def looks_like_file_url(url: str) -> bool:
    return policy_looks_like_file_url(url)


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


def visible_text(node) -> str:
    """Plain text without Moodle screen-reader / accesshide chrome."""
    clone = BeautifulSoup(str(node), "html.parser")
    root = clone.body or clone
    for hidden in root.select(".sr-only, .accesshide, .visually-hidden"):
        hidden.decompose()
    return normalized_text(root)


def parse_course_page(html: str) -> tuple[str, list[CourseActivity]]:
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one("h1") or soup.select_one("title")
    title = unescape_html(visible_text(title_node) if title_node else "BK-LMS course")
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
            "h3.sectionname a, h3.sectionname, h3.section-name, h3[data-for='section_title']"
        )
        section_title = unescape_html(
            visible_text(section_title_node) if section_title_node else "General"
        )
        activity_nodes = section.select('li.activity[data-for="cmitem"], li.activity')
        seen_nodes: set[str] = set()
        for activity in activity_nodes:
            key = activity.get("data-id") or activity.get("id") or str(id(activity))
            if key in seen_nodes:
                continue
            seen_nodes.add(key)

            item_type = activity_type(activity.get("class", []))
            link = activity.select_one(
                ".activityname a[href], a.aalink[href], .instancename, a[href]"
            )
            if link and not link.get("href"):
                link = activity.select_one("a.aalink[href], a[href]")
            url = urljoin(LMS_BASE, link["href"]) if link and link.get("href") else None
            named = activity.select_one("[data-activityname]")
            inst = activity.select_one(".instancename")
            if named and named.get("data-activityname"):
                item_title = named["data-activityname"].strip()
            elif inst:
                item_title = visible_text(inst)
            elif link:
                item_title = visible_text(link)
            else:
                item_title = visible_text(activity)
            item_title = re.sub(
                rf"\s+(?:{re.escape(item_type)}|assignment|file|url|page|quiz|folder)$",
                "",
                item_title,
                flags=re.IGNORECASE,
            ).strip()
            item_title = unescape_html(item_title)
            if not item_title:
                item_title = f"Untitled {item_type}"

            activities.append(
                CourseActivity(
                    title=item_title,
                    section=section_title,
                    item_type=item_type,
                    url=canonical_url(url) if url else None,
                    inline_text=visible_text(activity) if url is None else "",
                )
            )
    return title, activities


CHROME_SELECTORS = (
    "nav",
    ".secondary-navigation",
    ".drawer",
    ".block",
    ".breadcrumb",
    ".activity-navigation",
    "form[action*='logout']",
    "#page-header",
    "#page-footer",
    ".footer-popover",
)


def strip_chrome(region) -> None:
    for selector in CHROME_SELECTORS:
        for node in region.select(selector):
            node.decompose()


def discover_links(html: str, base_url: str, *, section: str = "", item_type: str = "", relation: str = "linked-from-page") -> list[LinkSeed]:
    soup = BeautifulSoup(html, "html.parser")
    region = main_region(soup)
    strip_chrome(region)
    seeds: list[LinkSeed] = []
    seen: set[str] = set()
    for tag in region.select("[href], [src]"):
        raw = tag.get("href") or tag.get("src")
        if not raw or raw.startswith("#"):
            continue
        target = canonical_url(urljoin(base_url, raw))
        if target in seen:
            continue
        seen.add(target)
        title = visible_text(tag) or Path(urlparse(target).path).name or target
        seeds.append(
            LinkSeed(
                url=target,
                title=title,
                section=section,
                item_type=item_type,
                relation=relation,
            )
        )
    return seeds


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
        context: BrowserContext | None = None,
    ) -> None:
        self.course_url = canonical_url(course_url)
        self.course_id = course_id_from_url(course_url)
        self.output_dir = output_dir
        self.profile_dir = profile_dir
        self.headless = headless
        self.max_pages = max_pages
        self.records: list[Record] = []
        self.audit_events: list[AuditEvent] = []
        self.html_followed = 0
        self.cap_hit = False
        self._external_context = context
        self.context: BrowserContext | None = context

    async def run(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "pages").mkdir(exist_ok=True)
        (self.output_dir / "files").mkdir(exist_ok=True)
        (self.output_dir / "raw").mkdir(exist_ok=True)

        if self._external_context is not None:
            self.context = self._external_context
            await self._run_with_context()
            return self.output_dir / "index.md"

        async with async_playwright() as p:
            self.context = await launch_persistent_lms_context(
                p, self.profile_dir, headless=self.headless
            )
            try:
                await self._run_with_context()
                await save_storage_state(self.context, self.profile_dir)
            finally:
                await self.context.close()

        return self.output_dir / "index.md"

    async def _run_with_context(self) -> None:
        assert self.context is not None
        page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self._open_authenticated_course(page)

        html = await page.content()
        (self.output_dir / "raw" / "course.html").write_text(html, encoding="utf-8")
        course_title, activities = parse_course_page(html)
        self.audit_events.append(
            AuditEvent(
                url=self.course_url,
                decision="followed",
                reason="course-landing",
                title=course_title,
                item_type="course",
                kind="landing",
                relation="root",
            )
        )

        queue: deque[LinkSeed] = deque()
        queued: set[str] = set()
        for item in activities:
            if item.url:
                url = canonical_url(item.url)
                queued.add(url)
                queue.append(
                    LinkSeed(
                        url=url,
                        title=item.title,
                        section=item.section,
                        item_type=item.item_type,
                    )
                )
            else:
                self.records.append(
                    Record(
                        kind="inline",
                        url=f"{self.course_url}#inline-{item.item_type}",
                        title=item.title,
                        section=item.section,
                        item_type=item.item_type,
                        relation="activity",
                        note=item.inline_text,
                    )
                )
                self.audit_events.append(
                    AuditEvent(
                        url=self.course_url,
                        decision="followed",
                        reason="inline-label",
                        title=item.title,
                        item_type=item.item_type,
                        kind="inline",
                        relation="activity",
                    )
                )

        for extra in discover_links(html, self.course_url):
            if extra.url in queued or extra.url == self.course_url:
                continue
            queued.add(extra.url)
            extra.section = extra.section or "General"
            extra.relation = extra.relation or "landing-link"
            queue.append(extra)

        await self._crawl_queue(page, queue)
        self._write_manifest()
        self._write_audit(course_title, activities)
        self._write_index(course_title, activities)

    async def _open_authenticated_course(self, page: Page) -> None:
        await page.goto(self.course_url, wait_until="commit", timeout=60_000)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=20_000)
        except Exception:
            pass
        if self._is_course_page(page.url):
            return
        await authenticate_page(page, headless=self.headless)
        if self.context is not None:
            await save_storage_state(self.context, self.profile_dir)
        await page.goto(self.course_url, wait_until="commit", timeout=60_000)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=20_000)
        except Exception:
            pass
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

    def _audit(self, event: AuditEvent) -> None:
        self.audit_events.append(event)

    async def _crawl_queue(self, page: Page, queue: deque[LinkSeed]) -> None:
        seen: set[str] = {self.course_url}
        remaining_after_cap: list[LinkSeed] = []
        while queue:
            seed = queue.popleft()
            url = canonical_url(seed.url)
            if url in seen:
                self._audit(
                    AuditEvent(
                        url=url,
                        decision="duplicate",
                        reason="already-seen",
                        title=seed.title,
                        item_type=seed.item_type,
                        relation=seed.relation,
                    )
                )
                continue

            decision = classify_url(url, self.course_id)
            if decision.action == "external":
                seen.add(url)
                self.records.append(
                    Record(
                        kind="external",
                        url=url,
                        title=seed.title,
                        section=seed.section,
                        item_type=seed.item_type,
                        relation=seed.relation,
                        note=decision.reason,
                    )
                )
                self._audit(
                    AuditEvent(
                        url=url,
                        decision="external",
                        reason=decision.reason,
                        title=seed.title,
                        item_type=seed.item_type,
                        kind="external",
                        relation=seed.relation,
                    )
                )
                continue
            if decision.action == "exclude":
                seen.add(url)
                self.records.append(
                    Record(
                        kind="excluded",
                        url=url,
                        title=seed.title,
                        section=seed.section,
                        item_type=seed.item_type,
                        relation=seed.relation,
                        note=decision.reason,
                    )
                )
                self._audit(
                    AuditEvent(
                        url=url,
                        decision="excluded",
                        reason=decision.reason,
                        title=seed.title,
                        item_type=seed.item_type,
                        kind="excluded",
                        relation=seed.relation,
                    )
                )
                continue

            is_file = looks_like_file_url(url) or decision.reason in {
                "pluginfile",
                "file-extension",
                "folder-archive",
            }
            if not is_file and self.html_followed >= self.max_pages:
                self.cap_hit = True
                remaining_after_cap.append(seed)
                continue

            seen.add(url)
            if is_file:
                await self._capture_file(seed, url)
            else:
                discovered = await self._capture_html(page, seed, url)
                queue.extend(
                    item for item in discovered if canonical_url(item.url) not in seen
                )

        for seed in remaining_after_cap:
            url = canonical_url(seed.url)
            self.records.append(
                Record(
                    kind="excluded",
                    url=url,
                    title=seed.title,
                    section=seed.section,
                    item_type=seed.item_type,
                    relation=seed.relation,
                    note="safety-cap",
                )
            )
            self._audit(
                AuditEvent(
                    url=url,
                    decision="excluded",
                    reason="safety-cap",
                    title=seed.title,
                    item_type=seed.item_type,
                    kind="excluded",
                    relation=seed.relation,
                )
            )
        for seed in queue:
            url = canonical_url(seed.url)
            self.records.append(
                Record(
                    kind="excluded",
                    url=url,
                    title=seed.title,
                    section=seed.section,
                    item_type=seed.item_type,
                    relation=seed.relation,
                    note="safety-cap" if self.cap_hit else "unprocessed",
                )
            )
            self._audit(
                AuditEvent(
                    url=url,
                    decision="excluded",
                    reason="safety-cap" if self.cap_hit else "unprocessed",
                    title=seed.title,
                    item_type=seed.item_type,
                    kind="excluded",
                    relation=seed.relation,
                )
            )

    async def _capture_file(self, seed: LinkSeed, url: str) -> None:
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
            self._audit(
                AuditEvent(
                    url=url,
                    decision="external",
                    reason="file-redirect-external",
                    title=seed.title,
                    item_type=seed.item_type,
                    kind="external",
                    relation=seed.relation,
                )
            )
            return
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
            self._audit(
                AuditEvent(
                    url=url,
                    decision="error",
                    reason="request-failed",
                    title=seed.title,
                    item_type=seed.item_type,
                    kind="error",
                    relation=seed.relation,
                )
            )
            return
        content_type = response.headers.get("content-type", "").lower()
        body = await response.body()
        if "text/html" in content_type or "application/xhtml+xml" in content_type:
            record, _discovered = self._save_html(final_url, body, seed, content_type)
            self.records.append(record)
            self._audit(
                AuditEvent(
                    url=url,
                    decision="followed",
                    reason="file-url-returned-html",
                    title=record.title,
                    item_type=seed.item_type,
                    kind="page",
                    relation=seed.relation,
                )
            )
            return
        record = self._save_file(final_url, body, seed, response)
        self.records.append(record)
        self._audit(
            AuditEvent(
                url=url,
                decision="followed",
                reason="file",
                title=record.title,
                item_type=seed.item_type,
                kind="file",
                relation=seed.relation,
            )
        )

    async def _capture_html(self, page: Page, seed: LinkSeed, url: str) -> list[LinkSeed]:
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
            self._audit(
                AuditEvent(
                    url=url,
                    decision="external",
                    reason="html-redirect-external",
                    title=seed.title,
                    item_type=seed.item_type,
                    kind="external",
                    relation=seed.relation,
                )
            )
            return []
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
            self._audit(
                AuditEvent(
                    url=url,
                    decision="error",
                    reason="request-failed",
                    title=seed.title,
                    item_type=seed.item_type,
                    kind="error",
                    relation=seed.relation,
                )
            )
            return []

        content_type = response.headers.get("content-type", "").lower()
        body = await response.body()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            record = self._save_file(final_url, body, seed, response)
            self.records.append(record)
            self._audit(
                AuditEvent(
                    url=url,
                    decision="followed",
                    reason="module-view-file",
                    title=record.title,
                    item_type=seed.item_type,
                    kind="file",
                    relation=seed.relation,
                )
            )
            return []

        html = body.decode("utf-8", errors="replace")
        path = urlparse(url).path
        needs_js = (
            "/mod/folder/" in path
            or "/mod/scorm/" in path
            or "/mod/url/" in path
            or path == "/course/view.php"
        )
        if needs_js:
            browser_html = await self._browser_html(page, url)
            if browser_html:
                html, final_url = browser_html
                body = html.encode("utf-8")
                content_type = "text/html; charset=utf-8"

        self.html_followed += 1
        record, discovered = self._save_html(final_url, body, seed, content_type)
        self.records.append(record)
        self._audit(
            AuditEvent(
                url=url,
                decision="followed",
                reason=classify_url(url, self.course_id).reason,
                title=record.title,
                item_type=seed.item_type,
                kind="page",
                relation=seed.relation,
            )
        )
        return discovered

    async def _browser_html(self, page: Page, url: str) -> tuple[str, str] | None:
        try:
            await page.goto(url, wait_until="commit", timeout=60_000)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=15_000)
            except Exception:
                pass
            try:
                await page.wait_for_load_state("networkidle", timeout=6_000)
            except Exception:
                pass
        except Exception:
            return None
        final = canonical_url(page.url)
        if not is_lms_url(final):
            return None
        return await page.content(), final

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
                    timeout=120_000,
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
        strip_chrome(region)

        page_title_node = region.select_one("h1, h2") or soup.select_one("title")
        page_title = visible_text(page_title_node) if page_title_node else seed.title
        markdown = html_to_markdown(str(region), heading_style="ATX").strip()
        digest = hashlib.sha256(body).hexdigest()
        filename = sanitize_filename(seed.title or page_title)
        rel_path = Path("pages") / f"{filename}-{digest[:8]}.md"
        (self.output_dir / rel_path).write_text(
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

        discovered = discover_links(
            html,
            url,
            section=seed.section,
            item_type=seed.item_type,
            relation="linked-from-page",
        )

        return (
            Record(
                kind="page",
                url=seed.url,
                title=page_title or seed.title,
                section=seed.section,
                item_type=seed.item_type,
                relation=seed.relation,
                resolved_url=url if url != seed.url else None,
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
            url=seed.url,
            title=seed.title or name,
            section=seed.section,
            item_type=seed.item_type,
            relation=seed.relation,
            resolved_url=url if url != seed.url else None,
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
                "html_followed": self.html_followed,
                "max_pages": self.max_pages,
                "cap_hit": self.cap_hit,
            }
            fh.write(json.dumps(meta, ensure_ascii=False) + "\n")
            for record in self.records:
                fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def _write_audit(
        self, course_title: str, activities: list[CourseActivity]
    ) -> None:
        counts: dict[str, int] = {}
        for event in self.audit_events:
            counts[event.decision] = counts.get(event.decision, 0) + 1
        module_types = sorted({item.item_type for item in activities if item.item_type})
        error_count = sum(1 for record in self.records if record.kind == "error")
        payload = {
            "course_id": self.course_id,
            "course_title": course_title,
            "course_url": self.course_url,
            "scraped_at": utc_now_iso(),
            "max_pages": self.max_pages,
            "html_followed": self.html_followed,
            "cap_hit": self.cap_hit,
            "error_count": error_count,
            "complete": (not self.cap_hit) and error_count == 0,
            "module_types": module_types,
            "activity_count": len(activities),
            "counts": counts,
            "events": [asdict(event) for event in self.audit_events],
        }
        (self.output_dir / "audit.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

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
                "- Completeness audit: [audit.json](audit.json)",
                "- Original course landing page: [raw/course.html](raw/course.html)",
                "",
                "Interactive quiz attempts, submissions, forum discussions, and other stateful Moodle actions are excluded with reasons in audit.json.",
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

    return Path("../Personal-Knowledge-Vault")


async def crawl_course(
    course_url: str,
    *,
    pkv_root: Path | None = None,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    headless: bool = False,
    max_pages: int = 200,
    context: BrowserContext | None = None,
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
        context=context,
    )
    return await crawler.run()
