#[cfg(test)]
mod tests {
    use std::{
        fs,
        path::PathBuf,
        time::{SystemTime, UNIX_EPOCH},
    };

    use crate::commands::{
        LoginState, check_login, courses_payload, extract_sesskey, parse_courses_ajax,
        validate_netscape_cookie_file, write_course_snapshot_json,
    };
    use lms_core::models::CourseSummary;
    use lms_core::parser::parse_course_snapshot;
    use reqwest::StatusCode;

    #[test]
    fn accepts_valid_netscape_cookie_file() {
        let content = "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tTRUE\t2147483647\tsessionid\tabc123\n";

        assert!(validate_netscape_cookie_file(content).is_ok());
    }

    #[test]
    fn rejects_wrong_header() {
        let content = "not a netscape cookie file\n.example.com\tTRUE\t/\tTRUE\t2147483647\tsessionid\tabc123\n";

        assert!(validate_netscape_cookie_file(content).is_err());
    }

    #[test]
    fn rejects_malformed_cookie_line() {
        let content =
            "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tTRUE\t2147483647\tsessionid\n";

        assert!(validate_netscape_cookie_file(content).is_err());
    }

    #[test]
    fn check_login_detects_unauthorized_status() {
        let state = check_login(StatusCode::UNAUTHORIZED, "https://lms.hcmut.edu.vn/my");

        assert!(matches!(state, LoginState::Unauthorized));
    }

    #[test]
    fn check_login_detects_redirect_to_login() {
        let state = check_login(StatusCode::OK, "https://lms.hcmut.edu.vn/login/index.php");

        assert!(matches!(state, LoginState::RedirectedToLogin));
    }

    #[test]
    fn check_login_detects_logged_in_state() {
        let state = check_login(StatusCode::OK, "https://lms.hcmut.edu.vn/my");

        assert!(matches!(state, LoginState::LoggedIn));
    }

    #[test]
    fn extracts_sesskey_from_html() {
        let html = r#"<html><script>"sesskey":"abc123xyz"</script></html>"#;

        let sesskey = extract_sesskey(html).unwrap();

        assert_eq!(sesskey, "abc123xyz");
    }

    #[test]
    fn errors_when_sesskey_is_missing() {
        let html = "<html><body>no sesskey here</body></html>";

        assert!(extract_sesskey(html).is_err());
    }

    #[test]
    fn parses_courses_ajax_and_sorts_by_id() {
        let json = r#"
        [
          {
            "data": {
              "courses": [
                { "id": 20, "fullname": "Systems", "viewurl": "https://example.com/course/20" },
                { "id": 10, "fullname": "Algorithms" }
              ]
            }
          }
        ]
        "#;

        let courses = parse_courses_ajax(json).unwrap();

        assert_eq!(courses.len(), 2);
        assert_eq!(courses[0].id, 10);
        assert_eq!(courses[0].fullname, "Algorithms");
        assert_eq!(courses[0].course_code, "");
        assert_eq!(courses[0].lecturer, "");
        assert_eq!(courses[0].education_program, "");
        assert_eq!(courses[0].semester, "");
        assert!(courses[0].group_classes.is_empty());
        assert_eq!(courses[0].viewurl, "");
        assert_eq!(courses[1].id, 20);
    }

    #[test]
    fn courses_payload_does_not_request_enddate() {
        let payload = courses_payload();
        let payload_text = payload.to_string();

        assert!(!payload_text.contains("enddate"));
    }

    #[test]
    fn rejects_empty_courses_ajax_response() {
        let json = "[]";

        assert!(parse_courses_ajax(json).is_err());
    }

    #[test]
    fn reports_courses_ajax_error_envelope() {
        let json = r#"
        [
          {
            "error": true,
            "exception": {
              "message": "Invalid sesskey"
            }
          }
        ]
        "#;

        let err = parse_courses_ajax(json).unwrap_err().to_string();

        assert!(err.contains("courses ajax returned an error"));
        assert!(err.contains("Invalid sesskey"));
    }

    #[test]
    fn reports_courses_ajax_missing_data() {
        let json = r#"[{ "error": false }]"#;

        let err = parse_courses_ajax(json).unwrap_err().to_string();

        assert!(err.contains("courses ajax response missing data"));
    }

    #[test]
    fn writes_parsed_course_snapshot_to_json_file() {
        let fixture_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..")
            .join("data")
            .join("course_pages")
            .join("course_134167.html");
        let html = fs::read_to_string(&fixture_path).expect("read course fixture");
        let snapshot = parse_course_snapshot(
            CourseSummary {
                id: 134167,
                fullname: "Linear Algebra".to_string(),
                course_code: "MT1007".to_string(),
                lecturer: "Đặng Thị Kim Nhung".to_string(),
                education_program: "CLC".to_string(),
                semester: "HK252".to_string(),
                group_classes: vec![
                    "CC02".to_string(),
                    "CC03".to_string(),
                    "CC04".to_string(),
                    "CC05".to_string(),
                    "CC06".to_string(),
                    "CC07".to_string(),
                    "CC08".to_string(),
                ],
                viewurl: "https://lms.hcmut.edu.vn/course/view.php?id=134167".to_string(),
            },
            &html,
        )
        .expect("parse snapshot");

        let temp_name = format!(
            "course_sections_test_{}.json",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system time")
                .as_nanos()
        );
        let output_path = std::env::temp_dir().join(temp_name);

        write_course_snapshot_json(&output_path, &snapshot).expect("write json");

        let written = fs::read_to_string(&output_path).expect("read written json");
        let parsed_back: lms_core::models::CourseSnapshot =
            serde_json::from_str(&written).expect("parse written json");

        assert_eq!(parsed_back, snapshot);

        let _ = fs::remove_file(output_path);
    }
}
