# BK-LMS Scraper

Local-first exporter for **HCMUT BK-LMS**.

The project is no longer a Rust-learning exercise. v0 has one concrete job:

> Log into BK-LMS in a local browser, crawl a course's useful Moodle content, and export a durable retrieval snapshot into Personal-Knowledge-Vault.

The old Rust code remains in the repository as legacy/reference material, but the active implementation is Python.

## What v0 does

Given a course such as:

```text
https://lms.hcmut.edu.vn/course/view.php?id=11267
```

it:

- opens Chromium with a **persistent local profile**;
- lets you complete HCMUT/SSO login yourself when needed;
- extracts the course section/activity map;
- recursively follows bounded, content-bearing Moodle pages;
- downloads LMS-hosted files such as PDFs, slides, documents, archives, and media;
- turns useful HTML page bodies into Markdown;
- records external links without crawling the external site;
- writes everything into `PKV/lms/courses/<course-id>/`.

It deliberately does **not** implement syncing, diffs, notifications, scheduling, databases, or AI indexing yet.

It also does not recursively mirror forum discussions, quiz attempts, or submission workflows.

## Security model

Do not put your HCMUT password in code, prompts, `.env`, or this repository.

The crawler launches a browser and you log in yourself. Chromium keeps the authenticated session in `.bk-lms-profile/`, which is git-ignored. The generated PKV export contains course content but no copied browser cookie store.

If your PKV is synced to GitHub, make sure its visibility and your rights to store course materials there are appropriate.

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

## Export course 11267

If your PKV is at the historical Windows location, this is enough:

```bash
bk-lms crawl 11267
```

Otherwise point to it explicitly:

```bash
bk-lms crawl 11267 --pkv /path/to/Personal-Knowledge-Vault
```

or set:

```bash
PKV_PATH=/path/to/Personal-Knowledge-Vault
```

On the first run, Chromium opens. Complete the university login there, then return to the terminal and press Enter. The browser profile is reused later.

Once a working session exists, unattended/headless retrieval is possible:

```bash
bk-lms crawl 11267 --headless
```

v0 overwrites the course export in place. That is intentional: it is a snapshot exporter, not a sync/history engine.

## Output

```text
Personal-Knowledge-Vault/
  lms/
    courses/
      11267/
        index.md
        manifest.jsonl
        raw/
          course.html
        pages/
          ...
        files/
          ...
```

`index.md` is the human/AI entry point. `manifest.jsonl` is the machine-readable map containing original URLs, local paths, item type, section, content type, and SHA-256 hashes.

This gives future agents a small durable surface to query before they ever need to touch the LMS.

## Crawl boundary

The crawler does **not** blindly recurse through the entire Moodle site.

It follows selected content routes (`assign`, `book`, `folder`, `lesson`, `page`, `quiz`, `resource`, `url`, `wiki`) and LMS-hosted files. Global navigation, profiles, dashboards, other courses, and external sites are not traversed. A `--max-pages` cap adds a second guardrail.
