# BK-LMS Scraper

Local-first exporter for **HCMUT BK-LMS**.

v0 has one concrete job:

> Authenticate to BK-LMS from local configuration, discover the user's Semester 1 2026-2027 courses, crawl useful Moodle content, and export durable retrieval snapshots into Personal-Knowledge-Vault.

The active implementation is Python. The older Rust and TypeScript implementations remain as reference material.

## v0 target

Semester 1 of academic year 2026-2027 is represented by the LMS course-title token `HK261`.

```bash
bk-lms crawl-semester HK261
```

The command:

1. reuses or establishes an authenticated local Chromium profile;
2. discovers all enrolled courses through Moodle's authenticated course-overview AJAX API;
3. selects course full names containing `HK261`;
4. runs the existing bounded per-course crawler for every match;
5. writes one semester index plus the normal per-course snapshots into PKV.

A single course can still be exported directly:

```bash
bk-lms crawl 11267
```

## Local credentials

Copy the template:

```bash
cp .env.example .env
```

Set your own HCMUT credentials in the local `.env`:

```dotenv
BK_LMS_USERNAME=your_bknetid
BK_LMS_PASSWORD=your_hcmut_sso_password
BK_LMS_SEMESTER=HK261
```

`.env` is git-ignored. **Never commit it or paste its contents into prompts/issues.** The password exists locally in plaintext, so protect the machine/account and restrict access to the repository directory.

The crawler attempts the HCMUT CAS/SSO browser login automatically when credentials are configured. The authenticated Chromium session is retained in `.bk-lms-profile/`, which is also git-ignored. If SSO changes or requires an interactive step, a non-headless run can fall back to manual browser login.

## Install

Python 3.11+:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -e .
playwright install chromium
```

Optional tests:

```bash
pip install -e ".[dev]"
pytest
```

## Export Semester 1 2026-2027

With `.env` configured:

```bash
bk-lms crawl-semester
```

`HK261` is the v0 default. You can also provide the token explicitly:

```bash
bk-lms crawl-semester HK261
```

For an already-valid browser profile and fully unattended execution:

```bash
bk-lms crawl-semester HK261 --headless
```

Point to PKV explicitly when needed:

```bash
bk-lms crawl-semester HK261 --pkv /path/to/Personal-Knowledge-Vault
```

or set:

```bash
PKV_PATH=/path/to/Personal-Knowledge-Vault
```

## Output

```text
Personal-Knowledge-Vault/
  lms/
    semesters/
      HK261/
        index.md
        manifest.json
    courses/
      <course-id>/
        index.md
        manifest.jsonl
        raw/
          course.html
        pages/
          ...
        files/
          ...
```

The semester index lists every matched course. Each course `index.md` is the human/AI entry point; `manifest.jsonl` records original URLs, local paths, item type, section, content type, and SHA-256 hashes.

v0 overwrites each course export in place. It is a snapshot exporter, not yet a sync/history engine.

## What course crawling includes

For each course the crawler:

- extracts the course section/activity map;
- recursively follows bounded, content-bearing Moodle pages;
- downloads LMS-hosted PDFs, slides, documents, archives, images, and media;
- turns useful HTML page bodies into Markdown;
- records external links without crawling the external site.

It follows selected Moodle content routes (`assign`, `book`, `folder`, `lesson`, `page`, `quiz`, `resource`, `url`, `wiki`) and LMS-hosted files. Global navigation, profiles, dashboards, other courses, and external sites are not recursively traversed. `--max-pages` provides a second guardrail per course.

Interactive quiz attempts, submission workflows, and forum discussions are deliberately not mirrored in v0.

## Security and scope

- Use only your own HCMUT account and content you are authorized to access.
- `.env` and `.bk-lms-profile/` must remain local and uncommitted.
- The scraper is read-only; it does not submit assignments, attempts, forms, or grades.
- It does not bypass CAPTCHA, MFA, or other interactive security controls.
- If PKV is synced to GitHub, ensure its visibility and your right to store course materials there are appropriate.
