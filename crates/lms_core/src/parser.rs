use anyhow::{Context, anyhow};
use scraper::{ElementRef, Html, Selector};

use crate::models::{CourseItem, CourseSection, CourseSnapshot, CourseSummary, ParseWarning};

pub fn parse_course_summary_from_html(
    id: i64,
    viewurl: String,
    html: &str,
) -> anyhow::Result<CourseSummary> {
    let document = Html::parse_document(html);
    let title_selector = selector("title")?;
    let title = document
        .select(&title_selector)
        .next()
        .map(normalized_text)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| anyhow!("course title not found"))?;

    Ok(parse_course_summary_from_title(id, viewurl, &title))
}

pub fn parse_course_summary_from_title(id: i64, viewurl: String, title: &str) -> CourseSummary {
    let title = title.trim().strip_prefix("Course:").unwrap_or(title).trim();
    let title = title.split('|').next().unwrap_or(title).trim();

    let (before_groups, group_classes) = extract_group_classes(title);
    let (before_semester, education_program, semester) =
        extract_program_and_semester(&before_groups);
    let (course_part, lecturer) = before_semester
        .split_once('_')
        .map(|(course, lecturer)| (course.trim(), lecturer.trim()))
        .unwrap_or((before_semester.trim(), ""));
    let (fullname, course_code) = extract_course_name_and_code(course_part);

    CourseSummary {
        id,
        fullname,
        course_code,
        lecturer: lecturer.to_string(),
        education_program,
        semester,
        group_classes,
        viewurl,
    }
}

pub fn parse_course_snapshot(course: CourseSummary, html: &str) -> anyhow::Result<CourseSnapshot> {
    let document = Html::parse_document(html);
    let section_selector = selector(r#"li.section[data-for="section"]"#)?;

    let mut sections = Vec::new();
    let mut parse_warnings = Vec::new();
    for section in document.select(&section_selector) {
        let (section, warnings) = parse_section(section)?;
        sections.push(section);
        parse_warnings.extend(warnings);
    }

    Ok(CourseSnapshot {
        course,
        sections,
        parse_warnings,
    })
}

fn extract_group_classes(title: &str) -> (String, Vec<String>) {
    if let (Some(start), Some(end)) = (title.rfind('['), title.rfind(']')) {
        if start < end {
            let groups = title[start + 1..end]
                .split(',')
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(str::to_string)
                .collect();
            return (title[..start].trim().to_string(), groups);
        }
    }

    (title.trim().to_string(), Vec::new())
}

fn extract_program_and_semester(title: &str) -> (String, String, String) {
    if let (Some(start), Some(end)) = (title.rfind('('), title.rfind(')')) {
        if start < end {
            let value = title[start + 1..end].trim();
            if let Some((program, semester)) = value.split_once('_') {
                return (
                    title[..start].trim().to_string(),
                    program.trim().to_string(),
                    semester.trim().to_string(),
                );
            }
        }
    }

    (title.trim().to_string(), String::new(), String::new())
}

fn extract_course_name_and_code(course_part: &str) -> (String, String) {
    let course_part = course_part.trim();
    if let (Some(start), Some(end)) = (course_part.rfind('('), course_part.rfind(')')) {
        if start < end && end == course_part.len() - 1 {
            return (
                course_part[..start].trim().to_string(),
                course_part[start + 1..end].trim().to_string(),
            );
        }
    }

    (course_part.to_string(), String::new())
}

fn parse_section(section: ElementRef<'_>) -> anyhow::Result<(CourseSection, Vec<ParseWarning>)> {
    let title_selector = selector("h3.sectionname a")?;
    let activity_selector = selector(r#"ul[data-for="cmlist"] > li.activity[data-for="cmitem"]"#)?;

    let id = required_attr(section, "data-id", "section data-id")?;
    let number = required_attr(section, "data-number", "section data-number")?;
    let title = section
        .select(&title_selector)
        .next()
        .map(normalized_text)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| anyhow!("section title not found"))?;

    let mut items = Vec::new();
    let mut warnings = Vec::new();
    for activity in section.select(&activity_selector) {
        match parse_item(activity) {
            Ok(item) => items.push(item),
            Err(err) => warnings.push(ParseWarning {
                section_id: id.clone(),
                section_number: number.clone(),
                activity_id: activity.value().attr("data-id").map(str::to_string),
                message: err.to_string(),
            }),
        }
    }

    Ok((
        CourseSection {
            id,
            number,
            title,
            items,
        },
        warnings,
    ))
}

fn parse_item(activity: ElementRef<'_>) -> anyhow::Result<CourseItem> {
    let id = required_attr(activity, "data-id", "activity data-id")?;
    let class_attr = required_attr(activity, "class", "activity class")?;
    let item_type =
        extract_item_type(&class_attr).ok_or_else(|| anyhow!("activity type not found"))?;

    let (url, url_kind) = extract_activity_url(activity, &id)?;
    let title = extract_activity_title(activity, &item_type, &id)?;

    Ok(CourseItem {
        id,
        title,
        url,
        url_kind,
        item_type,
        due_raw: None,
        due_at: None,
    })
}

fn extract_activity_url(activity: ElementRef<'_>, id: &str) -> anyhow::Result<(String, String)> {
    let activity_name_link_selector = selector(".activityname a")?;
    let any_link_selector = selector(r#"a[href]"#)?;

    let url = activity
        .select(&activity_name_link_selector)
        .next()
        .or_else(|| activity.select(&any_link_selector).next())
        .map(|link| required_attr(link, "href", "activity href"))
        .transpose()?;
    
    match url {
        Some(url) => Ok((url, "direct".to_string())),
        None => Ok((format!("#module-{id}"), "module_anchor".to_string())),

    }
}

fn extract_activity_title(
    activity: ElementRef<'_>,
    item_type: &str,
    id: &str,
) -> anyhow::Result<String> {
    let title_selector = selector(".instancename")?;
    let activity_card_selector = selector("[data-activityname]")?;
    let any_link_selector = selector(r#"a[href]"#)?;

    let title = activity
        .select(&title_selector)
        .next()
        .map(normalized_text)
        .or_else(|| {
            activity
                .value()
                .attr("data-activityname")
                .map(str::to_string)
        })
        .or_else(|| {
            activity
                .select(&activity_card_selector)
                .find_map(|element| {
                    element
                        .value()
                        .attr("data-activityname")
                        .map(str::to_string)
                })
        })
        .or_else(|| {
            activity
                .select(&any_link_selector)
                .next()
                .map(normalized_text)
        })
        .or_else(|| {
            let text = normalized_text(activity);
            (!text.is_empty()).then_some(text)
        })
        .unwrap_or_else(|| format!("Untitled activity {id}"));

    let title = strip_activity_type_suffix(&title, item_type);
    if title.is_empty() {
        Ok(format!("Untitled activity {id}"))
    } else {
        Ok(title)
    }
}

fn strip_activity_type_suffix(title: &str, item_type: &str) -> String {
    let suffixes = [
        item_type,
        match item_type {
            "assign" => "assignment",
            "resource" => "file",
            "url" => "url",
            "forum" => "forum",
            "page" => "page",
            "questionnaire" => "questionnaire",
            "quiz" => "quiz",
            "folder" => "folder",
            _ => item_type,
        },
    ];

    let Some((prefix, suffix)) = title.rsplit_once(char::is_whitespace) else {
        return title.trim().to_string();
    };

    if suffixes
        .iter()
        .any(|expected| suffix.eq_ignore_ascii_case(expected))
    {
        prefix.trim().to_string()
    } else {
        title.trim().to_string()
    }
}

fn extract_item_type(class_attr: &str) -> Option<String> {
    class_attr
        .split_whitespace()
        .find_map(|class_name| class_name.strip_prefix("modtype_").map(str::to_string))
}

fn required_attr(element: ElementRef<'_>, attr: &str, label: &str) -> anyhow::Result<String> {
    element
        .value()
        .attr(attr)
        .map(str::to_string)
        .with_context(|| format!("{label} missing"))
}

fn normalized_text(element: ElementRef<'_>) -> String {
    element
        .text()
        .collect::<Vec<_>>()
        .join(" ")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn selector(css: &str) -> anyhow::Result<Selector> {
    Selector::parse(css).map_err(|_| anyhow!("invalid selector: {css}"))
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::path::PathBuf;

    use super::{
        parse_course_snapshot, parse_course_summary_from_html, parse_course_summary_from_title,
    };
    #[test]
    fn parses_course_title_metadata() {
        let summary = parse_course_summary_from_title(
            134167,
            "https://lms.hcmut.edu.vn/course/view.php?id=134167".to_string(),
            "Course: Linear Algebra (MT1007)_Đặng Thị Kim Nhung (CLC_HK252) [CC02,CC03,CC04,CC05,CC06,CC07,CC08] | BK-LMS",
        );

        assert_eq!(summary.id, 134167);
        assert_eq!(summary.fullname, "Linear Algebra");
        assert_eq!(summary.course_code, "MT1007");
        assert_eq!(summary.lecturer, "Đặng Thị Kim Nhung");
        assert_eq!(summary.education_program, "CLC");
        assert_eq!(summary.semester, "HK252");
        assert_eq!(
            summary.group_classes,
            ["CC02", "CC03", "CC04", "CC05", "CC06", "CC07", "CC08"]
        );
        assert_eq!(
            summary.viewurl,
            "https://lms.hcmut.edu.vn/course/view.php?id=134167"
        );
    }

    #[test]
    fn parses_sections_and_activity_items_from_saved_course_page() {
        let fixture_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..")
            .join("data")
            .join("course_pages")
            .join("course_134167.html");
        let html = fs::read_to_string(&fixture_path).expect("read course fixture");
        let course = parse_course_summary_from_html(
            134167,
            "https://lms.hcmut.edu.vn/course/view.php?id=134167".to_string(),
            &html,
        )
        .expect("parse course summary");

        let snapshot = parse_course_snapshot(course, &html).expect("parse snapshot");

        assert_eq!(snapshot.course.id, 134167);
        assert_eq!(snapshot.course.fullname, "Linear Algebra");
        assert_eq!(snapshot.course.course_code, "MT1007");
        assert_eq!(snapshot.course.lecturer, "Đặng Thị Kim Nhung");
        assert_eq!(snapshot.course.education_program, "CLC");
        assert_eq!(snapshot.course.semester, "HK252");
        assert_eq!(
            snapshot.course.viewurl,
            "https://lms.hcmut.edu.vn/course/view.php?id=134167"
        );
        assert!(snapshot.parse_warnings.is_empty());
        assert!(!snapshot.sections.is_empty());

        let general = snapshot
            .sections
            .iter()
            .find(|section| section.title == "General")
            .expect("general section");
        assert!(!general.items.is_empty());
        assert_eq!(general.items[0].id, "619327");
        assert_eq!(general.items[0].item_type, "url");
        assert_eq!(general.items[0].title, "Linear Algebra (MT1007)_Video");
        assert_eq!(
            general.items[0].url,
            "https://lms.hcmut.edu.vn/mod/url/view.php?id=619327"
        );

        let quiz_section = snapshot
            .sections
            .iter()
            .find(|section| section.title == "Test 10% of the final grade")
            .expect("quiz section");
        assert_eq!(quiz_section.items[0].item_type, "quiz");
        assert_eq!(quiz_section.items[0].id, "641479");
    }

    #[test]
    fn parses_inline_label_activity_without_link() {
        let html = r#"
        <html>
          <title>Course: Introduction to Computing (CO1005)_Video | BK-LMS</title>
          <body>
            <li class="section course-section" data-for="section" data-id="411059" data-number="1">
              <h3 class="sectionname"><a>General</a></h3>
              <ul data-for="cmlist">
                <li class="activity activity-wrapper label modtype_label" data-for="cmitem" data-id="397567" id="module-397567" data-activityname="Starting C++ videos by Dr Han Duy Phan at youtube">
                  <div class="activity-item focus-control activityinline" data-activityname="Starting C++ videos by Dr Han Duy Phan at youtube" data-region="activity-card">
                    <div class="activity-altcontent"><p>Inline label content</p></div>
                  </div>
                </li>
              </ul>
            </li>
          </body>
        </html>
        "#;
        let course = parse_course_summary_from_html(
            5207,
            "https://lms.hcmut.edu.vn/course/view.php?id=5207".to_string(),
            html,
        )
        .expect("parse course summary");

        let snapshot = parse_course_snapshot(course, html).expect("parse snapshot");
        let item = &snapshot.sections[0].items[0];

        assert_eq!(item.id, "397567");
        assert_eq!(item.item_type, "label");
        assert_eq!(
            item.title,
            "Starting C++ videos by Dr Han Duy Phan at youtube"
        );
        assert_eq!(item.url, "#module-397567");
    }

    #[test]
    fn falls_back_to_link_text_for_activity_title() {
        let html = r#"
        <html>
          <title>Course: Example Course | BK-LMS</title>
          <body>
            <li class="section course-section" data-for="section" data-id="1" data-number="1">
              <h3 class="sectionname"><a>General</a></h3>
              <ul data-for="cmlist">
                <li class="activity activity-wrapper url modtype_url" data-for="cmitem" data-id="42" id="module-42">
                  <div class="activity-item">
                    <a href="https://example.com/video">Watch setup video</a>
                  </div>
                </li>
              </ul>
            </li>
          </body>
        </html>
        "#;
        let course = parse_course_summary_from_html(
            1,
            "https://lms.hcmut.edu.vn/course/view.php?id=1".to_string(),
            html,
        )
        .expect("parse course summary");

        let snapshot = parse_course_snapshot(course, html).expect("parse snapshot");
        let item = &snapshot.sections[0].items[0];

        assert_eq!(item.id, "42");
        assert_eq!(item.title, "Watch setup video");
        assert_eq!(item.url, "https://example.com/video");
    }

    #[test]
    fn uses_untitled_fallback_for_empty_activity() {
        let html = r#"
        <html>
          <title>Course: Example Course | BK-LMS</title>
          <body>
            <li class="section course-section" data-for="section" data-id="1" data-number="1">
              <h3 class="sectionname"><a>General</a></h3>
              <ul data-for="cmlist">
                <li class="activity activity-wrapper label modtype_label" data-for="cmitem" data-id="99" id="module-99">
                  <div class="activity-item"></div>
                </li>
              </ul>
            </li>
          </body>
        </html>
        "#;
        let course = parse_course_summary_from_html(
            1,
            "https://lms.hcmut.edu.vn/course/view.php?id=1".to_string(),
            html,
        )
        .expect("parse course summary");

        let snapshot = parse_course_snapshot(course, html).expect("parse snapshot");
        let item = &snapshot.sections[0].items[0];

        assert_eq!(item.id, "99");
        assert_eq!(item.title, "Untitled activity 99");
        assert_eq!(item.url, "#module-99");
    }

    #[test]
    fn records_warning_for_skipped_activity() {
        let html = r#"
        <html>
          <title>Course: Example Course | BK-LMS</title>
          <body>
            <li class="section course-section" data-for="section" data-id="1" data-number="1">
              <h3 class="sectionname"><a>General</a></h3>
              <ul data-for="cmlist">
                <li class="activity activity-wrapper" data-for="cmitem" data-id="99" id="module-99">
                  <div class="activity-item"></div>
                </li>
              </ul>
            </li>
          </body>
        </html>
        "#;
        let course = parse_course_summary_from_html(
            1,
            "https://lms.hcmut.edu.vn/course/view.php?id=1".to_string(),
            html,
        )
        .expect("parse course summary");

        let snapshot = parse_course_snapshot(course, html).expect("parse snapshot");

        assert_eq!(snapshot.sections.len(), 1);
        assert!(snapshot.sections[0].items.is_empty());
        assert_eq!(snapshot.parse_warnings.len(), 1);
        assert_eq!(snapshot.parse_warnings[0].section_id, "1");
        assert_eq!(snapshot.parse_warnings[0].section_number, "1");
        assert_eq!(
            snapshot.parse_warnings[0].activity_id.as_deref(),
            Some("99")
        );
        assert_eq!(
            snapshot.parse_warnings[0].message,
            "activity type not found"
        );
    }
}
