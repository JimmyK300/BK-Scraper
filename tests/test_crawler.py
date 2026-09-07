from bk_lms.crawler import (
    content_disposition_filename,
    course_id_from_url,
    discover_links,
    looks_like_file_url,
    parse_course_page,
    should_follow_html,
)
from bk_lms.discovery import (
    courses_payload,
    extract_sesskey,
    parse_courses_ajax,
    parse_dashboard_courses,
    select_semester_courses,
)


def test_url_scope():
    assert course_id_from_url(
        "https://lms.hcmut.edu.vn/course/view.php?id=11267"
    ) == "11267"
    assert should_follow_html(
        "https://lms.hcmut.edu.vn/mod/page/view.php?id=123"
    )
    assert should_follow_html(
        "https://lms.hcmut.edu.vn/mod/scorm/view.php?id=337446",
        "143335",
    )
    assert looks_like_file_url(
        "https://lms.hcmut.edu.vn/pluginfile.php/1/mod_resource/content/1/a.pdf"
    )
    assert not should_follow_html("https://lms.hcmut.edu.vn/user/profile.php?id=1")
    assert not should_follow_html("https://example.com/page")
    assert not should_follow_html(
        "https://lms.hcmut.edu.vn/mod/scorm/player.php?a=1",
        "143335",
    )


def test_discover_links_extracts_pluginfile_from_folder_html():
    html = """
    <html><body>
      <div id="region-main">
        <a href="/pluginfile.php/999/mod_folder/content/0/Lecture-01.pdf">Lecture-01</a>
        <a href="/mod/scorm/view.php?id=337446">SCORM package</a>
        <nav><a href="/my/">Dashboard chrome</a></nav>
      </div>
    </body></html>
    """
    seeds = discover_links(html, "https://lms.hcmut.edu.vn/mod/folder/view.php?id=1")
    urls = {seed.url for seed in seeds}
    assert (
        "https://lms.hcmut.edu.vn/pluginfile.php/999/mod_folder/content/0/Lecture-01.pdf"
        in urls
    )
    assert "https://lms.hcmut.edu.vn/mod/scorm/view.php?id=337446" in urls
    assert not any("/my/" in url for url in urls)


def test_course_parser_strips_moodle_accesshide_chrome():
    html = """
    <html><head><title>Course: Algorithms | BK-LMS</title></head>
    <body>
      <li class="section course-section" data-for="section">
        <div class="course-section-header" data-for="section_title">
          <label class="sr-only">Select section Week 1</label>
          <h3 class="h4 sectionname" data-for="section_title">
            <a href="/course/section.php?id=1">Week 1</a>
          </h3>
          <span class="collapseall">Collapse all</span>
        </div>
        <li class="activity modtype_resource" data-for="cmitem" data-id="9">
          <div class="activity-item" data-activityname="Lecture 1">
            <label class="sr-only">Select activity Lecture 1</label>
            <a href="/mod/resource/view.php?id=9" class="aalink">
              <span class="instancename">Lecture 1 <span class="accesshide"> File</span></span>
            </a>
            <div>This syllabus outlines the course objectives.</div>
          </div>
        </li>
      </li>
    </body></html>
    """
    title, items = parse_course_page(html)
    assert title == "Algorithms"
    assert items[0].section == "Week 1"
    assert items[0].title == "Lecture 1"
    assert items[0].item_type == "resource"


def test_course_parser_strips_label_accesshide_chrome():
    html = """
    <html><head><title>Course: Philosophy | BK-LMS</title></head>
    <body>
      <li class="section course-section" data-for="section">
        <h3 class="sectionname">Reminders</h3>
        <li class="activity modtype_label" data-for="cmitem" data-id="3">
          <div class="activity-item" data-activityname="Office hours">
            <label class="sr-only">Select activity Office hours</label>
            <div class="activity-altcontent">
              Office hours are on Tuesday. Please read the textbook first.
            </div>
          </div>
        </li>
      </li>
    </body></html>
    """
    title, items = parse_course_page(html)
    assert title == "Philosophy"
    assert items[0].item_type == "label"
    assert items[0].url is None
    assert items[0].title == "Office hours"
    assert "Select activity" not in items[0].inline_text
    assert "Office hours are on Tuesday" in items[0].inline_text


def test_course_parser_extracts_sections_and_activities():
    html = """
    <html><head><title>Course: Algorithms | BK-LMS</title></head>
    <body>
      <li class="section course-section" data-for="section">
        <h3 class="sectionname">Week 1</h3>
        <ul>
          <li class="activity modtype_resource" data-for="cmitem" data-id="9">
            <div class="activityname">
              <a href="/mod/resource/view.php?id=9">
                <span class="instancename">Lecture 1 file</span>
              </a>
            </div>
          </li>
        </ul>
      </li>
    </body></html>
    """
    title, items = parse_course_page(html)
    assert title == "Algorithms"
    assert len(items) == 1
    assert items[0].section == "Week 1"
    assert items[0].item_type == "resource"
    assert items[0].title == "Lecture 1"
    assert items[0].url == "https://lms.hcmut.edu.vn/mod/resource/view.php?id=9"


def test_content_disposition_filename():
    assert (
        content_disposition_filename('attachment; filename="lecture.pdf"')
        == "lecture.pdf"
    )


def test_dashboard_parser_prefers_descriptive_course_title():
    html = """
    <div>
      <a href="/course/view.php?id=100">View</a>
      <a href="https://lms.hcmut.edu.vn/course/view.php?id=100">
        Data Structures (CO2003)_LECTURER (CLC_HK261) [CC01]
      </a>
      <a href="/course/view.php?id=200">
        Old Course (CO1000)_LECTURER (CLC_HK252)
      </a>
    </div>
    """
    courses = parse_dashboard_courses(html)
    assert [course.course_id for course in courses] == ["100", "200"]
    assert courses[0].title.startswith("Data Structures")

    selected = select_semester_courses(courses, "hk261")
    assert [course.course_id for course in selected] == ["100"]


def test_ajax_course_discovery_and_semester_filter():
    html = '<script>window.M = {"sesskey":"abc123"};</script>'
    assert extract_sesskey(html) == "abc123"
    payload = courses_payload()
    assert payload[0]["methodname"] == (
        "core_course_get_enrolled_courses_by_timeline_classification"
    )

    response = [
        {
            "error": False,
            "data": {
                "courses": [
                    {
                        "id": 20,
                        "fullname": "Computer Architecture (CO2007)_A (CLC_HK261)",
                        "viewurl": "https://lms.hcmut.edu.vn/course/view.php?id=20",
                    },
                    {
                        "id": 10,
                        "fullname": "Old Course (CO1000)_B (CLC_HK252)",
                        "viewurl": "/course/view.php?id=10",
                    },
                ]
            },
        }
    ]
    courses = parse_courses_ajax(response)
    assert [course.course_id for course in courses] == ["10", "20"]
    assert [course.course_id for course in select_semester_courses(courses, "HK261")] == [
        "20"
    ]
