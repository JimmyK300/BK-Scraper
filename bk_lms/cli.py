from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .crawler import DEFAULT_PROFILE_DIR, LMS_BASE, crawl_course, default_pkv_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bk-lms",
        description="Export one authenticated HCMUT BK-LMS course into PKV.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    crawl = sub.add_parser("crawl", help="crawl and export one Moodle course")
    crawl.add_argument(
        "course",
        help="numeric course id or full https://lms.hcmut.edu.vn/course/view.php?id=... URL",
    )
    crawl.add_argument(
        "--pkv",
        type=Path,
        default=default_pkv_root(),
        help="Personal-Knowledge-Vault root (or set PKV_PATH)",
    )
    crawl.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help="persistent browser profile used only for LMS session state",
    )
    crawl.add_argument(
        "--headless",
        action="store_true",
        help="reuse an already-authenticated profile without showing Chromium",
    )
    crawl.add_argument(
        "--max-pages",
        type=int,
        default=200,
        help="safety cap for recursively followed Moodle content pages",
    )
    return parser


def course_url(value: str) -> str:
    if value.isdigit():
        return f"{LMS_BASE}/course/view.php?id={value}"
    return value


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "crawl":
        index = asyncio.run(
            crawl_course(
                course_url(args.course),
                pkv_root=args.pkv,
                profile_dir=args.profile,
                headless=args.headless,
                max_pages=args.max_pages,
            )
        )
        print(f"\nExport complete: {index}")


if __name__ == "__main__":
    main()
