from bk_lms.crawler import (
    content_disposition_filename,
    course_id_from_url,
    looks_like_file_url,
    parse_course_page,
    should_follow_html,
)


def test_url_scope():
    assert course_id_from_url(
        "https://lms.hcmut.edu.vn/course/view.php?id=11267"
    ) == "11267"
    assert should_follow_html(
        "https://lms.hcmut.edu.vn/mod/page/view.php?id=123"
    )
    assert looks_like_file_url(
        "https://lms.hcmut.edu.vn/pluginfile.php/1/mod_resource/content/1/a.pdf"
    )
    assert not should_follow_html("https://lms.hcmut.edu.vn/user/profile.php?id=1")
    assert not should_follow_html("https://example.com/page")


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
