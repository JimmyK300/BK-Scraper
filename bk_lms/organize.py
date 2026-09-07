from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .crawler import default_pkv_root


COURSE_CODE_RE = re.compile(r"\(([A-Z]{2}\d{4})\)")

FAMILIES: dict[str, dict[str, str]] = {
    "GeneralChemistry": {
        "codes": "CH1003, CH1004",
        "title": "General Chemistry",
        "folder": "GeneralChemistry",
    },
    "DataStructuresAlgorithms": {
        "codes": "CO2003, CO2004",
        "title": "Data Structures and Algorithms",
        "folder": "DataStructuresAlgorithms",
    },
    "ComputerArchitecture": {
        "codes": "CO2007, CO2008",
        "title": "Computer Architecture",
        "folder": "ComputerArchitecture",
    },
    "MathematicalModeling": {
        "codes": "CO2011",
        "title": "Mathematical Modeling",
        "folder": "MathematicalModeling",
    },
    "ScientificThinkingSkills": {
        "codes": "SK2001",
        "title": "Scientific Thinking Skills",
        "folder": "ScientificThinkingSkills",
    },
    "MarxistLeninistPhilosophy": {
        "codes": "SP1031",
        "title": "Marxist–Leninist Philosophy",
        "folder": "MarxistLeninistPhilosophy",
    },
    "_Administration": {
        "codes": "LCN",
        "title": "Administration / homeroom",
        "folder": "_Administration",
    },
}

CODE_TO_FAMILY = {
    "CH1003": "GeneralChemistry",
    "CH1004": "GeneralChemistry",
    "CO2003": "DataStructuresAlgorithms",
    "CO2004": "DataStructuresAlgorithms",
    "CO2007": "ComputerArchitecture",
    "CO2008": "ComputerArchitecture",
    "CO2011": "MathematicalModeling",
    "SK2001": "ScientificThinkingSkills",
    "SP1031": "MarxistLeninistPhilosophy",
    "LCN": "_Administration",
}


@dataclass
class CourseMeta:
    course_id: str
    title: str
    url: str
    code: str
    family: str
    role: str
    empty: bool
    complete: bool
    cap_hit: bool
    error_count: int
    module_types: list[str]
    records: list[dict]
    audit_path: Path
    index_path: Path
    raw_dir: Path


def course_code_from_title(title: str) -> str:
    match = COURSE_CODE_RE.search(title)
    if match:
        return match.group(1)
    if "Lớp Chủ nhiệm" in title or "(LCN)" in title:
        return "LCN"
    return "UNKNOWN"


def infer_role(title: str, code: str) -> str:
    lower = title.lower()
    if code == "LCN" or "lớp chủ nhiệm" in lower:
        return "homeroom"
    if "project" in lower:
        return "projects"
    # Department-wide _ALL shells (no CLC lecturer section) even if the
    # title also contains Practice/Lab wording.
    if re.search(r"_ALL\b", title) and "CLC" not in title:
        return "global_shell"
    if "(lab)" in lower or " (lab)" in lower:
        return "lab"
    if "practice" in lower:
        return "practice"
    return "lecturer_section"


def rel_from(materials_file: Path, target: Path) -> str:
    return Path(os_relpath(target, materials_file.parent)).as_posix()


def os_relpath(target: Path, start: Path) -> str:
    return os_path_rel(target, start)


def os_path_rel(target: Path, start: Path) -> str:
    import os

    return os.path.relpath(target, start)


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_course(raw_dir: Path, fallback_title: str = "", fallback_url: str = "") -> CourseMeta:
    course_id = raw_dir.name
    manifest_rows = load_jsonl(raw_dir / "manifest.jsonl")
    header = next((row for row in manifest_rows if row.get("kind") == "crawl"), {})
    records = [row for row in manifest_rows if row.get("kind") != "crawl"]
    audit = {}
    audit_path = raw_dir / "audit.json"
    if audit_path.is_file():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    title = audit.get("course_title") or fallback_title or f"Course {course_id}"
    url = (
        audit.get("course_url")
        or header.get("course_url")
        or fallback_url
        or f"https://lms.hcmut.edu.vn/course/view.php?id={course_id}"
    )
    code = course_code_from_title(title)
    family = CODE_TO_FAMILY.get(code, "_Unmapped")
    empty = not any(row.get("kind") in {"file", "page"} for row in records)
    return CourseMeta(
        course_id=course_id,
        title=title,
        url=url,
        code=code,
        family=family,
        role=infer_role(title, code),
        empty=empty,
        complete=bool(audit.get("complete", False)),
        cap_hit=bool(audit.get("cap_hit", header.get("cap_hit", False))),
        error_count=int(audit.get("error_count", 0)),
        module_types=list(audit.get("module_types") or []),
        records=records,
        audit_path=audit_path,
        index_path=raw_dir / "index.md",
        raw_dir=raw_dir,
    )


def mark_parallel_sections(courses: list[CourseMeta]) -> None:
    by_code: dict[str, list[CourseMeta]] = defaultdict(list)
    for course in courses:
        if course.role == "lecturer_section":
            by_code[course.code].append(course)
    for group in by_code.values():
        if len(group) > 1:
            for course in group:
                course.role = "parallel_lecturer_section"


def md_link(label: str, path: str) -> str:
    # Parentheses and spaces in filenames would otherwise truncate CommonMark links.
    if any(ch in path for ch in "() "):
        return f"[{label}](<{path}>)"
    return f"[{label}]({path})"


def write_family_readme(family_dir: Path, family_key: str, courses: list[CourseMeta]) -> None:
    info = FAMILIES[family_key]
    lines = [
        "---",
        f'title: "{info["title"]} — HK261 materials"',
        "type: semester-subject-materials",
        "status: active",
        "tags: [materials, hk261]",
        "source_of_truth: this note",
        "---",
        "",
        f"# {info['title']}",
        "",
        f"- Course codes: `{info['codes']}`",
        f"- Semester: HK261",
        "- Raw scrape provenance lives under `lms/courses/<id>/`; this page links, it does not copy large files.",
        "",
        "## Source course instances",
        "",
        "| Course ID | Role | Code | Empty | Completeness | Title | Raw |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for course in sorted(courses, key=lambda item: item.course_id):
        raw = rel_from(family_dir / "README.md", course.index_path)
        audit = rel_from(family_dir / "README.md", course.audit_path) if course.audit_path.is_file() else ""
        complete = "complete" if course.complete and not course.empty else (
            "empty shell" if course.empty else ("cap hit" if course.cap_hit else "see audit")
        )
        lines.append(
            f"| `{course.course_id}` | {course.role} | `{course.code}` | "
            f"{'yes' if course.empty else 'no'} | {complete} | {course.title} | "
            f"{md_link('index', raw)}"
            + (f" · {md_link('audit', audit)}" if audit else "")
            + " |"
        )
    lines.extend(["", "## Materials by section", ""])

    if all(course.empty for course in courses):
        lines.extend(
            [
                "No downloadable lesson files were present on these LMS shells at scrape time.",
                "",
            ]
        )
    else:
        for course in sorted(courses, key=lambda item: item.course_id):
            lines.append(f"### {course.title} (`{course.course_id}`)")
            lines.append("")
            if course.empty:
                lines.append("Empty LMS shell — no files or content pages captured.")
                lines.append("")
                continue
            by_section: dict[str, list[dict]] = defaultdict(list)
            for record in course.records:
                if record.get("kind") in {"excluded", "error"}:
                    continue
                by_section[record.get("section") or "General"].append(record)
            for section, items in by_section.items():
                lines.append(f"#### {section}")
                lines.append("")
                seen_urls: set[str] = set()
                for item in items:
                    url = item.get("url") or ""
                    key = f"{item.get('kind')}:{url}:{item.get('title')}"
                    if key in seen_urls:
                        continue
                    seen_urls.add(key)
                    kind = item.get("kind")
                    title = item.get("title") or kind
                    item_type = item.get("item_type") or ""
                    local = item.get("local_path")
                    source = item.get("resolved_url") or url
                    bits = [f"**{title}**"]
                    if item_type:
                        bits.append(f"`{item_type}`")
                    bits.append(f"`{kind}`")
                    if local:
                        target = course.raw_dir / local
                        rel = rel_from(family_dir / "README.md", target)
                        bits.append(md_link("local", rel))
                    if source:
                        bits.append(md_link("LMS", source))
                    if kind == "external":
                        bits.append("(external reference; not mirrored)")
                    if kind == "inline":
                        note = (item.get("note") or "").replace("\n", " ").strip()
                        if note:
                            bits.append(f"— {note[:240]}")
                    lines.append("- " + " ".join(bits))
                lines.append("")
            excluded = [row for row in course.records if row.get("kind") == "excluded"]
            interesting = [
                row
                for row in excluded
                if row.get("note")
                not in {
                    "course-chrome",
                    "theme-or-asset",
                    "site-chrome",
                    "same-course-landing",
                    "auth-chrome",
                }
            ]
            if interesting:
                lines.append("#### Intentional exclusions")
                lines.append("")
                reasons: dict[str, int] = defaultdict(int)
                for row in interesting:
                    reasons[str(row.get("note"))] += 1
                for reason, count in sorted(reasons.items()):
                    lines.append(f"- `{reason}` × {count}")
                lines.append("")
    (family_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_semester_readme(root: Path, courses: list[CourseMeta]) -> None:
    lines = [
        "---",
        'title: "HK261 Materials Index"',
        "date: 2026-09-07",
        "type: semester-materials-index",
        "status: active",
        "tags: [materials, hk261, semester-261]",
        "source_of_truth: this note",
        "manifest: ./_Index/manifest.csv",
        "---",
        "",
        "# HK261 Materials Index",
        "",
        "Semester 1 of academic year 2026–2027 (`HK261`).",
        "",
        "This folder is the **normalized learning-material surface** for agents and humans.",
        "Raw Moodle snapshots stay in `lms/courses/<id>/` and are linked, not copied.",
        "",
        "Active study notes are not created here. If a durable teaching track starts,",
        "`learning-manager` owns that later. HK252 subject folders (`Calc/`, `Discrete/`, …)",
        "are previous-semester active notes and are not HK261 owners.",
        "",
        "## Subject map",
        "",
        "| Folder | Subject | Course codes | LMS course IDs |",
        "| --- | --- | --- | --- |",
    ]
    by_family: dict[str, list[CourseMeta]] = defaultdict(list)
    for course in courses:
        by_family[course.family].append(course)
    for key in [
        "GeneralChemistry",
        "DataStructuresAlgorithms",
        "ComputerArchitecture",
        "MathematicalModeling",
        "ScientificThinkingSkills",
        "MarxistLeninistPhilosophy",
        "_Administration",
    ]:
        group = by_family.get(key, [])
        if not group:
            continue
        info = FAMILIES[key]
        ids = ", ".join(f"`{c.course_id}`" for c in sorted(group, key=lambda x: x.course_id))
        lines.append(
            f"| [{info['folder']}/](./{info['folder']}/README.md) | {info['title']} | `{info['codes']}` | {ids} |"
        )
    lines.extend(
        [
            "",
            "## Course instance → family",
            "",
            "| Course ID | Code | Role | Family | Empty | Completeness |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for course in sorted(courses, key=lambda item: item.course_id):
        status = (
            "empty shell"
            if course.empty
            else ("complete" if course.complete else ("cap hit" if course.cap_hit else "incomplete"))
        )
        lines.append(
            f"| `{course.course_id}` | `{course.code}` | {course.role} | `{course.family}` | "
            f"{'yes' if course.empty else 'no'} | {status} |"
        )
    complete_n = sum(1 for c in courses if c.complete or c.empty)
    cap_n = sum(1 for c in courses if c.cap_hit)
    err_n = sum(c.error_count for c in courses)
    lines.extend(
        [
            "",
            "## Completeness",
            "",
            f"- Source courses represented: **{len(courses)}**",
            f"- Courses with a closed audit (complete or verified empty): **{complete_n}**",
            f"- Safety-cap hits: **{cap_n}**",
            f"- Remaining crawler errors: **{err_n}**",
            "- Per-course audit: `lms/courses/<id>/audit.json`",
            "- Semester scrape index: [lms/semesters/HK261/index.md](../../lms/semesters/HK261/index.md)",
            "",
            "## Entry points",
            "",
            "- Start here for subject-level study material.",
            "- Use [_Index/manifest.csv](./_Index/manifest.csv) for agent retrieval across family, course ID, section, kind, and raw path.",
            "- Use [_Index/source-map.json](./_Index/source-map.json) for the machine-readable course map.",
            "- Use [_Index/audit-summary.json](./_Index/audit-summary.json) for completeness review.",
            "",
        ]
    )
    (root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_index(index_dir: Path, courses: list[CourseMeta]) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = index_dir / "manifest.csv"
    rows: list[dict[str, str]] = []
    for course in courses:
        for record in course.records:
            local = record.get("local_path") or ""
            raw_path = (
                f"lms/courses/{course.course_id}/{local}" if local else f"lms/courses/{course.course_id}/"
            )
            rows.append(
                {
                    "subject_family": course.family,
                    "course_code": course.code,
                    "course_id": course.course_id,
                    "course_title": course.title,
                    "role": course.role,
                    "section": record.get("section") or "",
                    "title": record.get("title") or "",
                    "item_type": record.get("item_type") or "",
                    "kind": record.get("kind") or "",
                    "source_url": record.get("resolved_url") or record.get("url") or "",
                    "raw_local_path": raw_path,
                    "relationship": record.get("relation") or "",
                    "exclusion_reason": record.get("note") if record.get("kind") == "excluded" else "",
                    "empty_shell": "true" if course.empty else "false",
                }
            )
    fieldnames = [
        "subject_family",
        "course_code",
        "course_id",
        "course_title",
        "role",
        "section",
        "title",
        "item_type",
        "kind",
        "source_url",
        "raw_local_path",
        "relationship",
        "exclusion_reason",
        "empty_shell",
    ]
    with manifest_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    source_map = {
        "semester": "HK261",
        "families": {
            key: {
                "title": FAMILIES[key]["title"],
                "codes": FAMILIES[key]["codes"],
                "courses": [
                    {
                        "course_id": c.course_id,
                        "title": c.title,
                        "code": c.code,
                        "role": c.role,
                        "empty": c.empty,
                        "complete": c.complete,
                        "url": c.url,
                        "raw": f"lms/courses/{c.course_id}/",
                    }
                    for c in sorted(group, key=lambda x: x.course_id)
                ],
            }
            for key, group in _by_family(courses).items()
            if key in FAMILIES
        },
    }
    (index_dir / "source-map.json").write_text(
        json.dumps(source_map, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    audit_summary = {
        "semester": "HK261",
        "course_count": len(courses),
        "complete_or_empty": sum(1 for c in courses if c.complete or c.empty),
        "cap_hits": [c.course_id for c in courses if c.cap_hit],
        "errors": {c.course_id: c.error_count for c in courses if c.error_count},
        "module_types": sorted({mod for c in courses for mod in c.module_types}),
        "courses": [
            {
                "course_id": c.course_id,
                "family": c.family,
                "role": c.role,
                "empty": c.empty,
                "complete": c.complete,
                "cap_hit": c.cap_hit,
                "error_count": c.error_count,
                "module_types": c.module_types,
                "audit": f"lms/courses/{c.course_id}/audit.json",
            }
            for c in sorted(courses, key=lambda x: x.course_id)
        ],
    }
    (index_dir / "audit-summary.json").write_text(
        json.dumps(audit_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _by_family(courses: list[CourseMeta]) -> dict[str, list[CourseMeta]]:
    grouped: dict[str, list[CourseMeta]] = defaultdict(list)
    for course in courses:
        grouped[course.family].append(course)
    return grouped


def organize_semester(semester: str = "HK261", pkv_root: Path | None = None) -> Path:
    root = (pkv_root or default_pkv_root()).expanduser()
    semester = semester.upper()
    semester_manifest = root / "lms" / "semesters" / semester / "manifest.json"
    courses_root = root / "lms" / "courses"
    metas: list[CourseMeta] = []
    if semester_manifest.is_file():
        payload = json.loads(semester_manifest.read_text(encoding="utf-8"))
        for item in payload.get("courses", []):
            course_id = str(item.get("course_id"))
            raw_dir = courses_root / course_id
            if raw_dir.is_dir():
                metas.append(
                    load_course(
                        raw_dir,
                        fallback_title=item.get("title") or "",
                        fallback_url=item.get("url") or "",
                    )
                )
    else:
        for raw_dir in sorted(courses_root.iterdir() if courses_root.is_dir() else []):
            if raw_dir.is_dir():
                metas.append(load_course(raw_dir))
    if not metas:
        raise RuntimeError(f"No scraped courses found to organize for {semester}.")
    mark_parallel_sections(metas)

    materials = root / "Materials" / semester
    materials.mkdir(parents=True, exist_ok=True)
    write_semester_readme(materials, metas)
    write_index(materials / "_Index", metas)
    grouped = _by_family(metas)
    for key, group in grouped.items():
        if key not in FAMILIES:
            continue
        family_dir = materials / FAMILIES[key]["folder"]
        family_dir.mkdir(parents=True, exist_ok=True)
        write_family_readme(family_dir, key, group)
    return materials / "README.md"
