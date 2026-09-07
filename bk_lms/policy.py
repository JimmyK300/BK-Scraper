from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FILE_EXTENSIONS = {
    ".7z", ".csv", ".doc", ".docx", ".epub", ".gif", ".jpeg", ".jpg",
    ".json", ".md", ".mp3", ".mp4", ".odp", ".ods", ".odt", ".pdf",
    ".png", ".ppt", ".pptx", ".rar", ".rtf", ".svg", ".txt", ".webm",
    ".webp", ".xls", ".xlsx", ".xml", ".zip",
}


# Stateful / private Moodle scripts. GET can still mutate attempt state.
STATEFUL_SCRIPTS = {
    "attempt.php",
    "comment.php",
    "delete.php",
    "discuss.php",
    "edit.php",
    "editsubmission.php",
    "mod.php",
    "override.php",
    "post.php",
    "processattempt.php",
    "report.php",
    "review.php",
    "submission.php",
    "summary.php",
    "user.php",
}

EXCLUDED_PREFIXES = (
    "/admin/",
    "/auth/",
    "/badges/",
    "/blog/",
    "/calendar/",
    "/comment/",
    "/draftfile.php/",
    "/enrol/",
    "/grade/",
    "/lib/",
    "/local/",
    "/login/",
    "/message/",
    "/my/",
    "/payment/",
    "/report/",
    "/tag/",
    "/theme/",
    "/user/",
)

CHROME_PATHS = {
    "/",
    "/help.php",
    "/course/edit.php",
    "/course/index.php",
    "/course/resources.php",
    "/course/search.php",
    "/course/section.php",
    "/course/user.php",
}


@dataclass(frozen=True, slots=True)
class LinkDecision:
    action: str  # follow | exclude | external
    reason: str


def classify_url(url: str, source_course_id: str) -> LinkDecision:
    """Classify one URL for read-only instructional crawl.

    Every LMS URL must be follow or exclude with a reason. External sites
    are recorded, never recursively mirrored.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme in {"javascript", "mailto", "data", "blob"}:
        return LinkDecision("exclude", "non-http")
    if scheme not in {"http", "https"}:
        return LinkDecision("exclude", "non-http")
    if parsed.netloc != "lms.hcmut.edu.vn":
        return LinkDecision("external", "external-site")

    path = parsed.path or "/"
    if path.startswith(EXCLUDED_PREFIXES):
        if path.startswith("/user/"):
            return LinkDecision("exclude", "private-user")
        if path.startswith("/grade/") or path.startswith("/message/"):
            return LinkDecision("exclude", "private-or-stateful")
        if path.startswith("/login/") or path.startswith("/auth/"):
            return LinkDecision("exclude", "auth-chrome")
        if path.startswith("/theme/") or path.startswith("/lib/"):
            return LinkDecision("exclude", "theme-or-asset")
        if path.startswith("/draftfile.php/"):
            return LinkDecision("exclude", "draft-file")
        return LinkDecision("exclude", "site-chrome")

    if path in CHROME_PATHS:
        return LinkDecision("exclude", "course-chrome")

    if path.startswith("/pluginfile.php/"):
        return LinkDecision("follow", "pluginfile")

    suffix = Path(path).suffix.lower()
    if suffix in FILE_EXTENSIONS:
        return LinkDecision("follow", "file-extension")

    if path == "/course/view.php":
        ids = parse_qs(parsed.query).get("id", [])
        other_id = ids[0] if ids and ids[0].isdigit() else None
        if not other_id:
            return LinkDecision("exclude", "course-chrome")
        if other_id == source_course_id:
            return LinkDecision("exclude", "same-course-landing")
        return LinkDecision("follow", "linked-course-landing")

    mod = _module_parts(path)
    if mod:
        module, script = mod
        if script in STATEFUL_SCRIPTS:
            return LinkDecision("exclude", f"stateful:{module}/{script}")
        if script == "view.php":
            return LinkDecision("follow", f"module-view:{module}")
        if module == "scorm" and script in {"player.php", "loadSCO.php"}:
            return LinkDecision("exclude", "interactive-scorm-player")
        if module == "folder" and script == "download_folder.php":
            return LinkDecision("follow", "folder-archive")
        if script == "index.php":
            return LinkDecision("exclude", f"module-index-chrome:{module}")
        return LinkDecision("exclude", f"unrecognized-module-script:{module}/{script}")

    if path.startswith("/mod/"):
        return LinkDecision("exclude", "unrecognized-mod-path")

    return LinkDecision("exclude", "unrecognized-lms-path")


def _module_parts(path: str) -> tuple[str, str] | None:
    parts = [part for part in path.split("/") if part]
    if len(parts) != 3 or parts[0] != "mod":
        return None
    script = parts[2]
    if not script.endswith(".php"):
        return None
    return parts[1], script


def should_follow_html(url: str, source_course_id: str = "") -> bool:
    decision = classify_url(url, source_course_id)
    if decision.action != "follow":
        return False
    if decision.reason in {"pluginfile", "file-extension", "folder-archive"}:
        return False
    return True


def looks_like_file_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc != "lms.hcmut.edu.vn":
        return False
    if parsed.path.startswith("/pluginfile.php/"):
        return True
    if Path(parsed.path).suffix.lower() in FILE_EXTENSIONS:
        return True
    if parsed.path.endswith("/download_folder.php"):
        return True
    return False
