from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .crawler import DEFAULT_PROFILE_DIR, LMS_BASE, crawl_course, default_pkv_root


@dataclass(slots=True)
class CourseLink:
    course_id: str
    title: str
    url: str


def _course_id(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc != "lms.hcmut.edu.vn":
        return None
    values = parse_qs(parsed.query).get("id", [])
    return values[0] if values and values[0].isdigit() else None


def parse_dashboard_courses(html: str) -> list[CourseLink]:
    """Fallback parser for Moodle pages that render course links in HTML."""
    soup = BeautifulSoup(html, "html.parser")
    by_id: dict[str, CourseLink] = {}

    for link in soup.select('a[href*="/course/view.php?id="]'):
        href = link.get("href")
        if not href:
            continue
        url = urljoin(LMS_BASE, href)
        course_id = _course_id(url)
        if not course_id:
            continue

        title = " ".join(link.stripped_strings).strip()
        card = link.find_parent(attrs={"data-course-id": True})
        if card:
            card_title = (
                card.get("data-course-name")
                or card.get("data-course-fullname")
                or ""
            ).strip()
            if card_title:
                title = card_title

        if not title:
            continue
        candidate = CourseLink(course_id=course_id, title=title, url=url)
        previous = by_id.get(course_id)
        if previous is None or len(candidate.title) > len(previous.title):
            by_id[course_id] = candidate

    return sorted(by_id.values(), key=lambda course: int(course.course_id))


def extract_sesskey(html: str) -> str:
    match = re.search(r'"sesskey":"([^"]+)"', html)
    if not match:
        raise RuntimeError("Moodle sesskey was not found on /my/courses.php")
    return match.group(1)


def courses_payload() -> list[dict[str, object]]:
    # Ported from the previous tested Rust implementation in this repository.
    return [
        {
            "index": 0,
            "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
            "args": {
                "offset": 0,
                "limit": 0,
                "classification": "all",
                "sort": "shortname",
                "customfieldname": "",
                "customfieldvalue": "",
            },
        }
    ]


def parse_courses_ajax(data: object) -> list[CourseLink]:
    if not isinstance(data, list) or not data:
        raise RuntimeError("Moodle courses AJAX returned an empty or malformed response")
    first = data[0]
    if not isinstance(first, dict):
        raise RuntimeError("Moodle courses AJAX response item is malformed")
    if first.get("error"):
        detail = first.get("exception") or "no exception details"
        raise RuntimeError(f"Moodle courses AJAX returned an error: {detail}")

    payload = first.get("data")
    if not isinstance(payload, dict) or not isinstance(payload.get("courses"), list):
        raise RuntimeError("Moodle courses AJAX response is missing data.courses")

    courses: list[CourseLink] = []
    for item in payload["courses"]:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        title = str(item.get("fullname") or "").strip()
        if raw_id is None or not str(raw_id).isdigit() or not title:
            continue
        course_id = str(raw_id)
        url = str(item.get("viewurl") or "").strip()
        if not url:
            url = f"{LMS_BASE}/course/view.php?id={course_id}"
        else:
            url = urljoin(LMS_BASE, url)
        courses.append(CourseLink(course_id=course_id, title=title, url=url))

    courses.sort(key=lambda course: int(course.course_id))
    return courses


def select_semester_courses(
    courses: list[CourseLink], semester_code: str
) -> list[CourseLink]:
    token = semester_code.strip().upper()
    if not token:
        raise ValueError("semester code must not be empty")
    return [course for course in courses if token in course.title.upper()]


async def discover_courses(
    *,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    headless: bool = True,
) -> list[CourseLink]:
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=headless,
            accept_downloads=False,
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(f"{LMS_BASE}/my/courses.php", wait_until="domcontentloaded")
            if urlparse(page.url).path.startswith("/login/"):
                raise RuntimeError(
                    "BK-LMS profile is not authenticated. Authenticate before course discovery."
                )
            html = await page.content()
            sesskey = extract_sesskey(html)
            service_url = (
                f"{LMS_BASE}/lib/ajax/service.php?sesskey={sesskey}"
                "&info=core_course_get_enrolled_courses_by_timeline_classification"
            )
            response = await context.request.post(service_url, data=courses_payload())
            if not response.ok:
                raise RuntimeError(
                    f"Moodle courses AJAX returned HTTP {response.status}"
                )
            return parse_courses_ajax(await response.json())
        finally:
            await context.close()


async def crawl_semester(
    semester_code: str,
    *,
    pkv_root: Path | None = None,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    max_pages: int = 200,
) -> Path:
    """Discover and export every enrolled course whose fullname contains semester_code."""
    root = (pkv_root or default_pkv_root()).expanduser()
    courses = select_semester_courses(
        await discover_courses(profile_dir=profile_dir, headless=True),
        semester_code,
    )
    if not courses:
        raise RuntimeError(
            f"No enrolled courses matched semester token {semester_code!r}."
        )

    results: list[dict[str, str]] = []
    for index, course in enumerate(courses, start=1):
        print(f"[{index}/{len(courses)}] {course.title} ({course.course_id})")
        output = await crawl_course(
            course.url,
            pkv_root=root,
            profile_dir=profile_dir,
            headless=True,
            max_pages=max_pages,
        )
        results.append({**asdict(course), "index_path": str(output)})

    semester_dir = root / "lms" / "semesters" / semester_code.upper()
    semester_dir.mkdir(parents=True, exist_ok=True)
    (semester_dir / "manifest.json").write_text(
        json.dumps(
            {
                "semester": semester_code.upper(),
                "course_count": len(courses),
                "courses": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    lines = [
        f"# BK-LMS {semester_code.upper()}",
        "",
        f"Courses exported: {len(courses)}",
        "",
    ]
    for course in courses:
        lines.append(
            f"- [{course.title}](../../courses/{course.course_id}/index.md) — `{course.course_id}`"
        )
    lines.extend(["", "Machine-readable list: [manifest.json](manifest.json)", ""])
    index_path = semester_dir / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path
