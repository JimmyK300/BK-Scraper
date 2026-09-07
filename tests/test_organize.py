import json
from pathlib import Path

from bk_lms.organize import (
    course_code_from_title,
    infer_role,
    mark_parallel_sections,
    organize_semester,
    CourseMeta,
)


def test_course_code_and_roles():
    assert course_code_from_title(
        "General Chemistry (CH1003)_LECTURE (CLC_HK261)"
    ) == "CH1003"
    assert course_code_from_title("Lớp Chủ nhiệm (LCN) HK261") == "LCN"
    assert infer_role("Data Structures Practice (CO2003)_HK261", "CO2003") == "practice"
    assert infer_role(
        "Data Structures and Algorithms (Practice) (CO2004)_HK261_ALL",
        "CO2004",
    ) == "global_shell"
    assert infer_role("Something_ALL (CLC_HK261)", "CO2003") != "global_shell"
    assert infer_role("DSA_ALL (HK261)", "CO2003") == "global_shell"
    assert infer_role(
        "General Chemistry (CH1003)_Projects_HK261_ALL", "CH1003"
    ) == "projects"
    assert infer_role("Lớp Chủ nhiệm K24", "LCN") == "homeroom"


def test_parallel_lecturer_sections():
    a = CourseMeta(
        course_id="1",
        title="A",
        url="",
        code="CO2011",
        family="MathematicalModeling",
        role="lecturer_section",
        empty=False,
        complete=True,
        cap_hit=False,
        error_count=0,
        module_types=[],
        records=[],
        audit_path=Path("x"),
        index_path=Path("y"),
        raw_dir=Path("z"),
    )
    b = CourseMeta(
        course_id="2",
        title="B",
        url="",
        code="CO2011",
        family="MathematicalModeling",
        role="lecturer_section",
        empty=False,
        complete=True,
        cap_hit=False,
        error_count=0,
        module_types=[],
        records=[],
        audit_path=Path("x"),
        index_path=Path("y"),
        raw_dir=Path("z"),
    )
    mark_parallel_sections([a, b])
    assert a.role == "parallel_lecturer_section"
    assert b.role == "parallel_lecturer_section"


def _write_course(root: Path, course_id: str, title: str, records: list[dict], empty: bool = False) -> None:
    raw = root / "lms" / "courses" / course_id
    raw.mkdir(parents=True)
    (raw / "index.md").write_text(f"# {title}\n", encoding="utf-8")
    audit = {
        "course_id": course_id,
        "course_title": title,
        "course_url": f"https://lms.hcmut.edu.vn/course/view.php?id={course_id}",
        "complete": True,
        "cap_hit": False,
        "error_count": 0,
        "module_types": ["resource"] if not empty else [],
    }
    (raw / "audit.json").write_text(json.dumps(audit), encoding="utf-8")
    lines = [
        json.dumps({"kind": "crawl", "course_id": course_id}),
        *[json.dumps(row) for row in records],
    ]
    (raw / "manifest.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if records and records[0].get("local_path"):
        path = raw / records[0]["local_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stub", encoding="utf-8")


def test_organize_semester_writes_family_indexes(tmp_path: Path):
    _write_course(
        tmp_path,
        "144076",
        "General Chemistry (CH1003)_LECTURE (CLC_HK261)",
        [
            {
                "kind": "file",
                "url": "https://lms.hcmut.edu.vn/mod/resource/view.php?id=1",
                "title": "Lecture 1",
                "section": "Week 1",
                "item_type": "resource",
                "local_path": "files/abc-lecture.pdf",
            }
        ],
    )
    _write_course(
        tmp_path,
        "147424",
        "Lớp Chủ nhiệm (LCN) HK261",
        [],
        empty=True,
    )
    semester = tmp_path / "lms" / "semesters" / "HK261"
    semester.mkdir(parents=True)
    (semester / "manifest.json").write_text(
        json.dumps(
            {
                "semester": "HK261",
                "courses": [
                    {"course_id": "144076", "title": "chem", "url": "u", "status": "ok"},
                    {"course_id": "147424", "title": "homeroom", "url": "u", "status": "ok"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (semester / "index.md").write_text("# HK261\n", encoding="utf-8")

    readme = organize_semester("HK261", pkv_root=tmp_path)
    materials = tmp_path / "Materials" / "HK261"
    assert readme == materials / "README.md"
    assert (materials / "GeneralChemistry" / "README.md").is_file()
    assert (materials / "_Administration" / "README.md").is_file()
    assert (materials / "_Index" / "manifest.csv").is_file()
    assert (materials / "_Index" / "source-map.json").is_file()
    chem = (materials / "GeneralChemistry" / "README.md").read_text(encoding="utf-8")
    assert "144076" in chem
    assert "Lecture 1" in chem
    assert "](<" in chem or "abc-lecture.pdf" in chem
    admin = (materials / "_Administration" / "README.md").read_text(encoding="utf-8")
    assert "empty" in admin.lower() or "Empty" in admin
    csv_text = (materials / "_Index" / "manifest.csv").read_text(encoding="utf-8")
    assert "GeneralChemistry" in csv_text
    assert "lms/courses/144076/files/abc-lecture.pdf" in csv_text
