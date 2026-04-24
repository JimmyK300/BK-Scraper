use dotenvy::dotenv;
use std::env;

#[derive(Debug, Clone)]
pub struct Config {
    pub moodle_base_url: String,
    pub moodle_cookie_jar_path: String,
    pub data_dir: String,
}

impl Config {
    pub fn build() -> Result<Self, String> {
        dotenv().ok();

        let moodle_base_url =
            env::var("MOODLE_BASE_URL").map_err(|_| "MOODLE_BASE_URL is missing".to_string())?;
        let moodle_cookie_jar_path = env::var("MOODLE_COOKIE_JAR_PATH")
            .ok()
            .unwrap_or("./cookie_jar".to_string());
        let data_dir = env::var("DATA_DIR")
            .ok()
            .unwrap_or("./data_dir".to_string());

        Ok(Self {
            moodle_base_url,
            moodle_cookie_jar_path,
            data_dir,
        })
    }
}
