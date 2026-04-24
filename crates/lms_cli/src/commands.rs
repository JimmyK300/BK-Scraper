use std::{
    fs::{self, File},
    io::BufWriter,
    path::{Path, PathBuf},
    sync::Arc,
};

use lms_core::{
    models::{CourseSnapshot, CourseSummary},
    parser::{parse_course_snapshot, parse_course_summary_from_html},
};
use reqwest::{Client, StatusCode, cookie::Jar};
use serde::Deserialize;
use tracing::{debug, info};

pub(crate) enum LoginState {
    Unauthorized,
    RedirectedToLogin,
    LoggedIn,
}

pub(crate) fn check_login(status: StatusCode, url: &str) -> LoginState {
    if status == StatusCode::UNAUTHORIZED {
        LoginState::Unauthorized
    } else if url.contains("login") {
        LoginState::RedirectedToLogin
    } else {
        LoginState::LoggedIn
    }
}
// Write one JSON file for one course.
// Add one test that checks the JSON parse/write flow.
// Add snapshot writing.
// For one course first, write data/courses/<id>.json with deterministic ordering.

// Add fixture-based tests for parsing.
// Save one real /my/courses AJAX sample and one course-page HTML sample, then test parsing from files instead of only inline strings.

fn load_cookie_jar(cookie_jar_path: &str) -> anyhow::Result<Arc<Jar>> {
    let cookie_text = std::fs::read_to_string(cookie_jar_path)?;
    let jar = Arc::new(Jar::default());

    for line in cookie_text.lines() {
        if line.starts_with('#') || line.trim().is_empty() {
            continue;
        }

        let fields: Vec<&str> = line.split('\t').collect();
        if fields.len() != 7 {
            continue;
        }

        let domain = fields[0];
        let path = fields[2];
        let name = fields[5];
        let value = fields[6];

        let cookie_url = reqwest::Url::parse(&format!(
            "https://{}{}",
            domain.trim_start_matches('.'),
            path
        ))?;

        jar.add_cookie_str(&format!("{}={}", name, value), &cookie_url);
    }

    Ok(jar)
}

pub async fn auth_check_fn(base_url: &str, cookie_jar_path: &str) -> anyhow::Result<String> {
    let jar = load_cookie_jar(cookie_jar_path)?;

    let client = reqwest::Client::builder().cookie_provider(jar).build()?;

    let base = reqwest::Url::parse(base_url)?;
    let url = base.join("/my")?;
    let response = client.get(url).send().await?;
    let url_parse = response.url().to_string();
    info!("connecting to: {}", url_parse);
    // info!(response);

    match check_login(response.status(), &url_parse) {
        LoginState::Unauthorized => Ok("Not logged in".to_string()),
        LoginState::RedirectedToLogin => Ok("Not logged in, redirected to login page".to_string()),
        LoginState::LoggedIn => Ok("Logged in!".to_string()),
    }
}

pub(crate) fn validate_netscape_cookie_file(content: &str) -> anyhow::Result<()> {
    let file_lines: Vec<&str> = content.lines().collect();

    if file_lines.is_empty() {
        return Err(anyhow::anyhow!("File is not of Netscape format"));
    }

    if file_lines[0] != "# Netscape HTTP Cookie File" {
        return Err(anyhow::anyhow!("File is not of Netscape format"));
    }

    for line in file_lines {
        if line == "# Netscape HTTP Cookie File" || line.starts_with('#') || line.is_empty() {
            continue;
        }

        let fields: Vec<&str> = line.split('\t').collect();
        if fields.len() != 7 || fields.iter().any(|field| field.is_empty()) {
            return Err(anyhow::anyhow!("Cookies lines malformed"));
        }
    }

    Ok(())
}

/// Imports a Netscape-format cookies file without logging any cookie contents.
pub async fn import_cookies_fn(input_path: PathBuf, output_path: String) -> anyhow::Result<String> {
    let content = fs::read_to_string(input_path)?;
    validate_netscape_cookie_file(&content)?;
    fs::write(output_path, content)?;
    Ok("Cookies imported!".to_string())
}

#[derive(Debug, Deserialize)]
struct CoursesAjaxItem {
    #[serde(default)]
    error: bool,
    data: Option<CoursesAjaxData>,
    exception: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
struct CoursesAjaxData {
    courses: Vec<CourseSummary>,
}

pub(crate) fn extract_sesskey(html: &str) -> anyhow::Result<String> {
    let marker = "\"sesskey\":\"";
    let start = html
        .find(marker)
        .ok_or_else(|| anyhow::anyhow!("sesskey not found in page"))?;

    let value_start = start + marker.len();
    let rest = &html[value_start..];

    let end = rest
        .find('"')
        .ok_or_else(|| anyhow::anyhow!("sesskey end quote not found"))?;

    Ok(rest[..end].to_string())
}

pub(crate) fn parse_courses_ajax(json_text: &str) -> anyhow::Result<Vec<CourseSummary>> {
    let mut items: Vec<CoursesAjaxItem> = serde_json::from_str(json_text)?;
    let first = items
        .pop()
        .ok_or_else(|| anyhow::anyhow!("empty ajax response"))?;

    if first.error {
        return Err(anyhow::anyhow!(
            "courses ajax returned an error: {}",
            format_ajax_exception(first.exception.as_ref())
        ));
    }

    let data = first.data.ok_or_else(|| {
        anyhow::anyhow!(
            "courses ajax response missing data: {}",
            format_ajax_exception(first.exception.as_ref())
        )
    })?;

    let mut courses = data.courses;
    courses.sort_by_key(|course| course.id);
    Ok(courses)
}

fn format_ajax_exception(exception: Option<&serde_json::Value>) -> String {
    let Some(exception) = exception else {
        return "no exception details".to_string();
    };

    if let Some(message) = exception.get("message").and_then(|value| value.as_str()) {
        return message.to_string();
    }

    exception.to_string()
}

pub(crate) fn write_course_snapshot_json(
    output_path: &Path,
    snapshot: &CourseSnapshot,
) -> anyhow::Result<()> {
    let file = File::create(output_path)?;
    let writer = BufWriter::new(file);
    serde_json::to_writer_pretty(writer, snapshot)?;
    Ok(())
}

pub(crate) fn courses_payload() -> serde_json::Value {
    serde_json::json!([
        {
            "index": 0,
            "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
            "args": {
                "offset": 0,
                "limit": 0,
                "classification": "all",
                "sort": "shortname",
                "customfieldname": "",
                "customfieldvalue": ""
            }
        }
    ])
}

async fn fetch_courses(client: &Client, service_url: &str) -> anyhow::Result<Vec<CourseSummary>> {
    let payload = courses_payload();
    debug!("courses ajax payload: {}", payload);

    let ajax_response_text = client
        .post(service_url)
        .json(&payload)
        .send()
        .await?
        .text()
        .await?;

    parse_courses_ajax(&ajax_response_text)
}

pub async fn courses_check_fn(
    base_url: &str,
    cookie_jar_path: &str,
) -> anyhow::Result<Vec<CourseSnapshot>> {
    let jar = load_cookie_jar(cookie_jar_path)?;

    let client = reqwest::Client::builder().cookie_provider(jar).build()?;

    let base = reqwest::Url::parse(base_url)?;
    let url = base.join("/my/courses.php")?;
    let response = client.get(url).send().await?;
    let url_parse = response.url().to_string();
    info!("connecting to: {}", url_parse);

    match check_login(response.status(), &url_parse) {
        LoginState::Unauthorized => Err(anyhow::anyhow!("Not logged in")),
        LoginState::RedirectedToLogin => {
            Err(anyhow::anyhow!("Not logged in, redirected to login page"))
        }
        LoginState::LoggedIn => {
            let html_body = response.text().await?;

            let sesskey = extract_sesskey(&html_body)?;

            let service_url = format!(
                "{}/lib/ajax/service.php?sesskey={}&info=core_course_get_enrolled_courses_by_timeline_classification",
                base_url.trim_end_matches('/'),
                sesskey
            );

            let courses = fetch_courses(&client, &service_url).await?;

            let mut course_snapshots = Vec::with_capacity(courses.len());

            for course in &courses {
                if !course.viewurl.starts_with("http") {
                    info!(
                        "skipping course_id {} because viewurl is not a course URL: {}",
                        course.id, course.viewurl
                    );
                    continue;
                }

                info!("course_id: {}", course.id);
                info!("title: {}", course.fullname);
                info!("url: {}", course.viewurl);

                let snapshot = fetch_one_course(&client, &course.viewurl, course).await?;

                fs::create_dir_all("data/courses")?;
                let path = format!("data/courses/{}.json", course.id);

                write_course_snapshot_json(Path::new(&path), &snapshot)?;

                course_snapshots.push(snapshot);
            }

            Ok(course_snapshots)
        }
    }
}

async fn fetch_one_course(
    client: &Client,
    url: &str,
    course_summary: &CourseSummary,
) -> anyhow::Result<CourseSnapshot> {
    let response = client.get(url).send().await?;

    //Write raw courses
    let html_body = response.text().await?;

    // let out_dir_raw = PathBuf::from("data/course_pages");
    // fs::create_dir_all(&out_dir_raw)?;
    // let out_path_raw = out_dir_raw.join(format!("course_{}.html", course_summary.id));
    // fs::write(&out_path_raw, &html_body)?;

    // //Write parsed courses
    // let out_dir = PathBuf::from("data/course");
    // fs::create_dir_all(&out_dir)?;
    // let out_path = out_dir.join(format!("course_{}.json", course_summary.id));
    // write_course_snapshot_json(&out_path, &course_snap)?;

    let course_snap = parse_course_snapshot(course_summary.clone(), &html_body)?;

    Ok(course_snap)
}

pub async fn fetch_one_course_by_id(
    base_url: &str,
    cookie_jar_path: &str,
    id: i64,
) -> anyhow::Result<CourseSnapshot> {
    let jar = load_cookie_jar(cookie_jar_path)?;

    let client = reqwest::Client::builder().cookie_provider(jar).build()?;

    let base = reqwest::Url::parse(base_url)?;
    let url = base.join(&format!("/course/view.php?id={id}"))?;
    let response = client.get(url).send().await?;
    let url_parse = response.url().to_string();
    info!("connecting to: {}", url_parse);

    match check_login(response.status(), &url_parse) {
        LoginState::Unauthorized => Err(anyhow::anyhow!("Not logged in")),
        LoginState::RedirectedToLogin => {
            Err(anyhow::anyhow!("Not logged in, redirected to login page"))
        }
        LoginState::LoggedIn => {
            let html_body = response.text().await?;
            let course_summary = parse_course_summary_from_html(id, url_parse, &html_body)?;

            parse_course_snapshot(course_summary, &html_body)
        }
    }
}
