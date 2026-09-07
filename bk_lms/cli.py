from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from .auth import ensure_authenticated_profile
from .crawler import DEFAULT_PROFILE_DIR, LMS_BASE, crawl_course, default_pkv_root
from .discovery import crawl_semester


def _shared_export_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--pkv",
        type=Path,
        default=default_pkv_root(),
        help="Personal-Knowledge-Vault root (or set PKV_PATH)",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help="persistent browser profile used only for LMS session state",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="authenticate/reuse the LMS session without showing Chromium",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=200,
        help="safety cap for recursively followed Moodle content pages per course",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bk-lms",
        description="Export authenticated HCMUT BK-LMS content into PKV.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    crawl = sub.add_parser("crawl", help="crawl and export one Moodle course")
    crawl.add_argument(
        "course",
        help="numeric course id or full https://lms.hcmut.edu.vn/course/view.php?id=... URL",
    )
    _shared_export_arguments(crawl)

    semester = sub.add_parser(
        "crawl-semester",
        help="discover dashboard courses for one HK token and export all of them",
    )
    semester.add_argument(
        "semester",
        nargs="?",
        default=os.environ.get("BK_LMS_SEMESTER", "HK261"),
        help="semester token contained in LMS course titles (default: BK_LMS_SEMESTER or HK261)",
    )
    _shared_export_arguments(semester)
    return parser


def course_url(value: str) -> str:
    if value.isdigit():
        return f"{LMS_BASE}/course/view.php?id={value}"
    return value


async def _run(args: argparse.Namespace) -> Path:
    await ensure_authenticated_profile(args.profile, headless=args.headless)

    if args.command == "crawl":
        return await crawl_course(
            course_url(args.course),
            pkv_root=args.pkv,
            profile_dir=args.profile,
            headless=args.headless,
            max_pages=args.max_pages,
        )

    if args.command == "crawl-semester":
        return await crawl_semester(
            args.semester,
            pkv_root=args.pkv,
            profile_dir=args.profile,
            max_pages=args.max_pages,
        )

    raise RuntimeError(f"Unknown command: {args.command}")


def main() -> None:
    # OS environment variables retain priority; .env fills only missing values.
    load_dotenv(override=False)
    args = build_parser().parse_args()
    output = asyncio.run(_run(args))
    print(f"\nExport complete: {output}")


if __name__ == "__main__":
    main()
