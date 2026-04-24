use std::path::PathBuf;

use clap::{Parser, Subcommand};
use clap_verbosity_flag::Verbosity;

use tracing::{error, info};
use tracing_subscriber::EnvFilter;

mod config_loader;
use config_loader::Config;

use lms_core::models::CourseSnapshot;

mod commands;
mod commands_test;
#[derive(Debug, Parser)]
#[command(name = "lms")]
struct Cli {
    #[command(subcommand)]
    command: Option<Command>,
    #[command(flatten)]
    verbosity: Verbosity,
}

#[derive(Subcommand, Debug)]
enum Command {
    AuthCheck,
    ImportCookies {
        #[arg(value_parser)]
        file: PathBuf,
    },
    Courses,
    FetchCourse {
        #[arg(value_parser)]
        id: i64,
    },
    Sync,
    Watch,
    Today,
    Export,
}

fn main() {
    dotenvy::dotenv().ok();

    let curr_config: Config;

    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    let rt = tokio::runtime::Runtime::new().unwrap();

    let cli: Cli = Cli::parse();

    match Config::build() {
        Ok(config) => {
            curr_config = config;
            info!("url: {}", curr_config.moodle_base_url);
            info!("cookie jar: {}", curr_config.moodle_cookie_jar_path);
            info!("data directory: {}", curr_config.data_dir);
        }
        Err(err) => {
            error!("Config error: {}", err);
            return;
        }
    }

    match cli.command {
        Some(Command::AuthCheck) => {
            let result: Result<String, anyhow::Error> = rt.block_on(async {
                commands::auth_check_fn(
                    &curr_config.moodle_base_url,
                    &curr_config.moodle_cookie_jar_path,
                )
                .await
            });

            match result {
                Ok(res) => {
                    info!(res);
                }
                Err(err) => {
                    error!("{}", err);
                }
            }
        }
        Some(Command::ImportCookies { file }) => {
            let result: Result<String, anyhow::Error> = rt.block_on(async {
                commands::import_cookies_fn(file, curr_config.moodle_cookie_jar_path).await
            });

            match result {
                Ok(res) => {
                    info!(res);
                }
                Err(err) => {
                    error!("{}", err);
                }
            }
        }
        Some(Command::Courses) => {
            let result: Result<Vec<CourseSnapshot>, anyhow::Error> = rt.block_on(async {
                commands::courses_check_fn(
                    &curr_config.moodle_base_url,
                    &curr_config.moodle_cookie_jar_path,
                )
                .await
            });

            match result {
                Ok(res) => {
                    println!("id\tfullname\tsections\tviewurl");
                    for snapshot in &res {
                        let course = &snapshot.course;
                        println!(
                            "{}\t{}\t{}\t{}",
                            course.id,
                            course.fullname,
                            snapshot.sections.len(),
                            course.viewurl
                        );
                    }
                    info!("There are {} courses", res.len())
                }
                Err(err) => {
                    error!("{}", err);
                }
            }
        }
        Some(Command::FetchCourse { id }) => {
            let result: Result<CourseSnapshot, anyhow::Error> = rt.block_on(async {
                commands::fetch_one_course_by_id(
                    &curr_config.moodle_base_url,
                    &curr_config.moodle_cookie_jar_path,
                    id,
                )
                .await
            });
            match result {
                Ok(snapshot) => {
                    println!("id\tfullname\tsections\tviewurl");
                    println!(
                        "{}\t{}\t{}\t{}",
                        snapshot.course.id,
                        snapshot.course.fullname,
                        snapshot.sections.len(),
                        snapshot.course.viewurl
                    );
                }
                Err(err) => {
                    error!("{}", err);
                }
            }
        }
        Some(Command::Sync) => {
            info!("hi")
        }
        Some(Command::Watch) => {
            info!("hi")
        }
        Some(Command::Today) => {
            info!("hi")
        }
        Some(Command::Export) => {
            info!("hi")
        }
        None => {
            info!("Welcome to LMS parser");
        }
    }

    ()
}
