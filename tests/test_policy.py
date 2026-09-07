from bk_lms.policy import classify_url, looks_like_file_url, should_follow_html


SOURCE = "143335"


def test_pluginfile_and_extensions_are_files_not_html_follows():
    pluginfile = (
        "https://lms.hcmut.edu.vn/pluginfile.php/123/mod_folder/content/0/Lecture-01.pdf"
    )
    decision = classify_url(pluginfile, SOURCE)
    assert decision.action == "follow"
    assert decision.reason == "pluginfile"
    assert looks_like_file_url(pluginfile)
    assert not should_follow_html(pluginfile, SOURCE)

    pptx = "https://lms.hcmut.edu.vn/files/Lecture-01.pptx"
    decision = classify_url(pptx, SOURCE)
    assert decision.action == "follow"
    assert decision.reason == "file-extension"
    assert looks_like_file_url(pptx)
    assert not should_follow_html(pptx, SOURCE)


def test_scorm_view_is_followed_player_is_excluded():
    view = "https://lms.hcmut.edu.vn/mod/scorm/view.php?id=337446"
    player = "https://lms.hcmut.edu.vn/mod/scorm/player.php?a=1"
    load = "https://lms.hcmut.edu.vn/mod/scorm/loadSCO.php?a=1"
    assert classify_url(view, SOURCE).action == "follow"
    assert classify_url(view, SOURCE).reason == "module-view:scorm"
    assert should_follow_html(view, SOURCE)
    assert classify_url(player, SOURCE) == classify_url(player, SOURCE)
    assert classify_url(player, SOURCE).action == "exclude"
    assert classify_url(player, SOURCE).reason == "interactive-scorm-player"
    assert classify_url(load, SOURCE).reason == "interactive-scorm-player"
    assert not should_follow_html(player, SOURCE)


def test_stateful_scripts_are_excluded_with_reason():
    attempt = "https://lms.hcmut.edu.vn/mod/quiz/attempt.php?attempt=1"
    discuss = "https://lms.hcmut.edu.vn/mod/forum/discuss.php?d=1"
    review = "https://lms.hcmut.edu.vn/mod/quiz/review.php?attempt=1"
    assert classify_url(attempt, SOURCE).reason == "stateful:quiz/attempt.php"
    assert classify_url(discuss, SOURCE).reason == "stateful:forum/discuss.php"
    assert classify_url(review, SOURCE).reason == "stateful:quiz/review.php"
    assert classify_url(attempt, SOURCE).action == "exclude"


def test_linked_course_landing_followed_same_course_excluded():
    same = "https://lms.hcmut.edu.vn/course/view.php?id=143335"
    other = "https://lms.hcmut.edu.vn/course/view.php?id=5387"
    assert classify_url(same, SOURCE).reason == "same-course-landing"
    assert classify_url(same, SOURCE).action == "exclude"
    assert classify_url(other, SOURCE).reason == "linked-course-landing"
    assert should_follow_html(other, SOURCE)


def test_unknown_module_script_is_never_silent():
    odd = "https://lms.hcmut.edu.vn/mod/resource/secret.php?id=1"
    decision = classify_url(odd, SOURCE)
    assert decision.action == "exclude"
    assert decision.reason == "unrecognized-module-script:resource/secret.php"

    unknown_path = "https://lms.hcmut.edu.vn/mystery/thing.php"
    decision = classify_url(unknown_path, SOURCE)
    assert decision.action == "exclude"
    assert decision.reason == "unrecognized-lms-path"


def test_external_and_folder_archive():
    ext = "https://drive.google.com/file/d/abc"
    assert classify_url(ext, SOURCE).action == "external"
    archive = "https://lms.hcmut.edu.vn/mod/folder/download_folder.php?id=9"
    assert classify_url(archive, SOURCE).reason == "folder-archive"
    assert looks_like_file_url(archive)
    assert not should_follow_html(archive, SOURCE)


def test_any_module_view_is_followed():
    for module in ("resource", "url", "page", "folder", "book", "lesson", "assign"):
        url = f"https://lms.hcmut.edu.vn/mod/{module}/view.php?id=1"
        decision = classify_url(url, SOURCE)
        assert decision.action == "follow", module
        assert decision.reason == f"module-view:{module}"
        assert should_follow_html(url, SOURCE)
