from __future__ import annotations

import json
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
    """Extract unique Moodle course links from an authenticated /my/ page."""
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
        # Dashboard cards can repeat a course with tiny labels such as "View".
        # Prefer the most descriptive text observed for that course id.
        if previous is None or len(candidate.title) > len(previous.title):
            by_id[course_id] = candidate

    return sorted(by_id.values(), key=lambda course: int(course.course_id))


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
            await page.goto(f"{LMS_BASE}/my/", wait_until="domcontentloaded")
            if urlparse(page.url).path.startswith("/login/"):
                raise RuntimeError(
                    "BK-LMS profile is not authenticated. Authenticate before course discovery."
                )
            return parse_dashboard_courses(await page.content())
        finally:
            await context.close()


async def crawl_semester(
    semester_code: str,
    *,
    pkv_root: Path | None = None,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    max_pages: int = 200,
) -> Path:
    """Discover and export every dashboard course whose title contains semester_code."""
    root = (pkv_root or default_pkv_root()).expanduser()
    courses = select_semester_courses(
        await discover_courses(profile_dir=profile_dir, headless=True),
        semester_code,
    )
    if not courses:
        raise RuntimeError(
            f"No dashboard courses matched semester token {semester_code!r}."
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
        results.append(
            {
                **asdict(course),
                "index_path": str(output),
            }
        )

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
