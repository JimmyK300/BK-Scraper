# Progress Notes

## Current Status

You have finished the first solid end-to-end slice for course discovery and initial course-page parsing.

What is working now:

- `auth-check` works with the cookie jar flow.
- `import-cookies` validates Netscape cookie files and has tests.
- `courses` fetches Moodle course summaries and prints them.
- `CourseSummary` was moved into `lms_core`.
- `CourseSnapshot`, `CourseSection`, and `CourseItem` now exist in `lms_core`.
- A real parser was added in `crates/lms_core/src/parser.rs`.
- The parser walks:
  - `li.section[data-for="section"]`
  - `ul[data-for="cmlist"] > li.activity[data-for="cmitem"]`
- The parser currently extracts:
  - section title
  - activity `data-id`
  - activity type from `modtype_*`
  - activity link
  - `.instancename` text
- A real saved fixture `data/course_pages/course_134167.html` is now being used in tests.

Test status:

- `cargo test -p lms_cli` passes.
- `cargo test -p lms_core` passes.

## What This Means

The project is no longer in the "just probing the site" phase.

You now have:

- a stable course discovery flow
- a saved real course page fixture
- a tested parser for sections and activity items
- the beginnings of a real snapshot model

This is a meaningful milestone because it gives you the shape needed for snapshot sync and later diff/event work.

## Important Current Limitations

- The parser currently includes hidden accessibility suffixes in titles, such as `URL` or `Quiz`.
- `due_raw` and `due_at` are still placeholders and are not being parsed yet.
- `fetch_one_course` currently saves HTML, but does not yet parse and write a JSON snapshot.
- Some CLI helper functions are `pub(crate)` only to support sibling-module tests.

## Next Steps

Recommended next sequence:

1. Integrate `lms_core::parser::parse_course_snapshot(...)` into the single-course fetch flow.
2. After fetching `course_<id>.html`, parse it into a `CourseSnapshot`.
3. Write one JSON snapshot file to `data/courses/<id>.json`.
4. Add one test for JSON snapshot writing and/or snapshot serialization.
5. Clean the parsed title so hidden Moodle suffixes like `URL` / `Quiz` do not pollute the stored title.
6. Add one more saved course-page fixture from another course to check parser stability.
7. Only after snapshot writing is stable, start the diff/event layer.

## Good Stopping Point

You can stop here safely.

When resuming, the highest-value next task is:

"Take one fetched course HTML file, parse it into `CourseSnapshot`, and save `data/courses/<id>.json`."
