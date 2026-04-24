use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CourseSummary {
    pub id: i64,
    pub fullname: String,
    #[serde(default)]
    pub course_code: String,
    #[serde(default)]
    pub lecturer: String,
    #[serde(default)]
    pub education_program: String,
    #[serde(default)]
    pub semester: String,
    #[serde(default)]
    pub group_classes: Vec<String>,
    #[serde(default)]
    pub viewurl: String,
}

impl CourseSummary {
    pub const MOODLE_REQUIRED_FIELDS: [&'static str; 3] = ["id", "fullname", "viewurl"];
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CourseSnapshot {
    pub course: CourseSummary,
    pub sections: Vec<CourseSection>,
    #[serde(default)]
    pub parse_warnings: Vec<ParseWarning>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ParseWarning {
    pub section_id: String,
    pub section_number: String,
    pub activity_id: Option<String>,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CourseSection {
    pub id: String,
    pub number: String,
    pub title: String,
    pub items: Vec<CourseItem>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CourseItem {
    pub id: String,
    pub title: String,
    pub url: String,
    pub url_kind: String,
    pub item_type: String,
    pub due_raw: Option<String>,
    pub due_at: Option<String>,
}
