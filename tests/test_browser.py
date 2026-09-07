import json
from pathlib import Path

from bk_lms.browser import load_storage_cookies, storage_state_path
from bk_lms.discovery import courses_payload


def test_storage_state_path_lives_inside_profile(tmp_path: Path):
    assert storage_state_path(tmp_path / "profile") == tmp_path / "profile" / "storage_state.json"


def test_load_storage_cookies_reads_playwright_payload(tmp_path: Path):
    profile = tmp_path / ".bk-lms-profile"
    profile.mkdir()
    payload = {
        "cookies": [
            {
                "name": "MoodleSession",
                "value": "abc",
                "domain": "lms.hcmut.edu.vn",
                "path": "/",
            }
        ]
    }
    (profile / "storage_state.json").write_text(json.dumps(payload), encoding="utf-8")
    cookies = load_storage_cookies(profile)
    assert cookies[0]["name"] == "MoodleSession"
    assert cookies[0]["value"] == "abc"


def test_load_storage_cookies_missing_or_corrupt(tmp_path: Path):
    profile = tmp_path / "empty"
    profile.mkdir()
    assert load_storage_cookies(profile) == []
    (profile / "storage_state.json").write_text("{not json", encoding="utf-8")
    assert load_storage_cookies(profile) == []


def test_courses_payload_is_json_serializable():
    payload = courses_payload()
    encoded = json.dumps(payload)
    assert "core_course_get_enrolled_courses_by_timeline_classification" in encoded
