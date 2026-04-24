# Project Proposal / PRD — HCMUT LMS Ingestion + Change Notifications + Export Workspace (Rust-first)

**Project codename:** HCMUT LMS Companion

**Document version:** 1.0

**Date:** 2026-04-12

**Status:** Final (approved for implementation)

## 1) Executive summary

HCMUT’s Moodle-based LMS contains all course materials and teacher updates, but it is not “attention-native”: changes are easy to miss because notifications remain inside the LMS. This project builds a **reliable ingestion + normalization pipeline** that:

1. authenticates to the LMS (SSO-friendly),
2. scrapes and normalizes course structure into a clean schema,
3. detects changes between syncs,
4. sends actionable notifications to phone/PC,
5. exports the structured data into the user’s **main personal repository** so studying/work happens in one place.

This is **not primarily an AI project**. The AI layer is optional and comes only after the data pipeline and structure are stable.

## 2) Problem statement

### Current pain

- Teachers update items (deadlines/resources/links), but LMS notifications do not reach the user’s phone/desktop.
- LMS content is messy: PDFs, pages, URLs, assignments, quizzes, forums.
- The user wants course work consolidated into an existing “main repo”, not spread across multiple places.
- The HCMUT login flow presents a “Tài khoản HCMUT” option (SSO-like), making standard username/password automation fragile.

### Why now

- Building this system is useful and aligns with the user’s goal of learning **backend development in Rust**.

## 3) Goals and non-goals

### Goals

- **G1 — Reliable access:** Achieve stable authenticated scraping even with the “Tài khoản HCMUT” entry point.
- **G2 — Clean structure:** Normalize courses into a consistent schema (Course → Sections → Items).
- **G3 — Real notifications:** Notify the user on phone/PC when content changes or deadlines change.
- **G4 — Single workspace:** Export outputs into the user’s main repository (data + minimal indexes).
- **G5 — Rust learning:** Implement the backend/CLI in Rust using idiomatic async + good structure.

### Non-goals (for MVP)

- Full web UI dashboard.
- Full AI tutoring assistant.
- Video transcription/subtitles ingestion.
- Automatic bypass of CAPTCHA / anti-bot measures.
- Storing or processing classmates’ personal data.

## 4) Users / personas

- **Primary user:** The repo owner (student) who wants actionable updates and a unified study workspace.
- **Secondary stakeholders:** None (initially single-user, local-first).

## 5) Scope (MVP)

### MVP capabilities

- Cookie/session-based authentication (SSO-friendly) with an explicit “session expired” notification.
- Course discovery from `/my/`.
- Course page scraping from `/course/view.php?id=...`.
- Item extraction (assignment/quiz/resource/page/url/forum/etc.) with stable identifiers where possible.
- Optional deadline enrichment by visiting assignment/quiz pages.
- Snapshot storage (JSON) + change detection (diff).
- Notification delivery via a single channel (Telegram or Discord).
- Export artifacts into another local repository path.

### Out of scope (MVP)

- PostgreSQL/pgvector indexing.
- Full-text content extraction for every PDF.
- Multi-user accounts.

## 6) Key constraints and assumptions

### Authentication reality

- The presence of “Tài khoản HCMUT” suggests SSO; direct username/password form POST may fail or change.
- Cookie-based sessions will expire; the system must attempt **automatic re-auth** when feasible and otherwise emit a dedicated `auth.session_expired` event + notification.
  - **MVP behavior:** reuse imported cookies; if expired, attempt a best-effort re-login if a non-SSO form is available; if not, notify and stop.
  - **Phase 2 option:** use a headless browser to complete the HCMUT SSO flow and refresh cookies automatically (only if policy/technical constraints allow it).

### Content variability

- Labels/dates may be in **English or Vietnamese**.
- Moodle HTML can change (themes/versions). Parsers must be resilient.

### Policy / compliance

- Use only with explicit permission and in compliance with school LMS rules.
- Rate-limit and avoid heavy scraping.

## 7) Decision log (confirmed + pending)

| Decision                     | Status        | Default / Recommendation                       | Notes                                                                                                      |
| ---------------------------- | ------------- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Implementation language      | **Confirmed** | Rust                                           | Primary learning goal (backend Rust).                                                                      |
| Interface                    | **Confirmed** | CLI-first                                      | Minimal UX: `sync`, `today`, `watch`, `export`.                                                            |
| Auth approach for MVP        | **Confirmed** | Cookie import + session reuse                  | Most robust for SSO. Best-effort auto re-auth is a stretch goal.                                           |
| Data store for MVP           | **Confirmed** | File-based JSON snapshots                      | Simple, debuggable, portable; DB later.                                                                    |
| Change detection             | **Confirmed** | Snapshot diff                                  | Produces notifications independent of Moodle’s internal notification UI.                                   |
| Notification channel         | **Confirmed** | Telegram                                       | Locked.                                                                                                    |
| Export target main repo path | **Confirmed** | `C:\Users\minhc\Code\Personal-Knowledge-Vault` | Base repository path; tool writes under a subdir.                                                          |
| Runtime model                | **Confirmed** | Local-first scheduled job                      | Runs on the user’s PC via Windows Task Scheduler (startup + interval). Always-on server is optional later. |
| Export formats               | **Confirmed** | JSON + minimal Markdown index                  | Locked.                                                                                                    |
| Auto-git commit/push         | **Confirmed** | Commit optional (default off)                  | Optional later; keep manual for MVP.                                                                       |
| Future API server            | **Optional**  | Axum                                           | Only if CLI isn’t enough; can be a later phase.                                                            |

## 8) Proposed system design

### High-level architecture

```mermaid
flowchart LR
  A[Browser login
Export cookies] --> B[Cookie importer
(tough-cookie/reqwest cookie store)]
  B --> C[Scraper
/my + /course/view]
  C --> D[Normalizer
Course→Sections→Items]
  D --> E[Snapshot store
JSON files]
  E --> F[Diff engine
Events]
  F --> G[Notifier
Telegram/Discord]
  E --> H[Exporter
writes to main repo]
```

### Components

1. **CLI (Rust)**
   - Commands: `auth-check`, `import-cookies`, `courses`, `sync`, `watch`, `today`, `export`.

2. **Auth module**
   - Cookie import (JSON / Netscape cookies.txt).
   - Session validation via `/my/`.
   - Detect expired session and emit a dedicated “re-auth required” event.

3. **Scraper module**
   - Fetch `/my/` and course pages.
   - Respect rate limits and concurrency.

4. **Normalizer**
   - Convert Moodle HTML into stable structured entities.
   - Tag types and extract due dates where possible.

5. **Storage**
   - **Snapshots**: one JSON file per course.
   - **Events log**: append-only JSONL or per-run event JSON.

6. **Notifier**
   - One output channel for MVP.

7. **Exporter**
   - Writes normalized snapshots + event logs into user’s main repository.

## 9) Data model (MVP)

### Normalized course snapshot

**Course**

- `source.base_url: string`
- `source.course_id: number`
- `source.scraped_at: ISO-8601 string`
- `title: string`
- `sections: Section[]`

**Section**

- `source.section_id?: string`
- `source.section_index?: number`
- `title: string`
- `items: Item[]`

**Item**

- `source.activity_id?: number` (when present)
- `source.mod_type?: string` (e.g., `assign`, `quiz`, `resource`)
- `source.url: string`
- `title: string`
- `kind: lecture | assignment | quiz | notes | unknown`
- `url: string`
- `due_at?: ISO-8601 string` (best effort)
- `due_raw?: string` (fallback)

### Event model (change log)

Each sync run emits events like:

- `auth.session_expired`
- `course.item_added`
- `course.item_removed`
- `course.item_title_changed`
- `course.item_due_changed`
- `course.resource_updated` (optional)

Event fields (recommended):

- `timestamp`
- `course_id`
- `course_title`
- `event_type`
- `item_key` (stable derived key: activity id if present, else URL)
- `before` / `after` (small diffs)
- `human_summary` (string)

## 10) Core workflows

### A) First-time setup

1. Log into LMS in browser.
2. Export cookies (JSON or Netscape cookies.txt).
3. Run `import-cookies`.
4. Run `auth-check`.
5. Run `courses` to list course ids.
6. Run `sync --all`.
7. Configure notifications (Telegram/Discord).
8. Run `watch --interval 15m`.
9. (Recommended) Register a startup + interval schedule (Windows Task Scheduler) so notifications run without manual commands.

### B) Session expired flow

- If `/my/` indicates login page or redirects to SSO without valid session:
  - Emit `auth.session_expired` event.
  - Send a notification: “Session expired — export cookies again.”
  - Stop scraping (avoid loops).

### C) Daily usage (action-focused)

- `today --days 7` shows upcoming deadlines.
- Notifications deliver changes and deadline updates.

### D) Export to main repo

- Exporter writes:
  - `lms/courses/<courseId>.json`
  - `lms/index.json`
  - `lms/events/<YYYY-MM-DD>.jsonl` (or per-run file)
  - `lms/README.md` (minimal index with links)

### E) Running continuously (runtime model)

**MVP target:** local-first.

- **Local computer (recommended):** run `watch` using Windows Task Scheduler (at logon/startup + repeat every 15 minutes).
- **Always-on server (optional later):** run the same `watch` command as a service (systemd/Docker). Requires careful secret handling and may increase auth complexity.

## 11) Functional requirements

### FR1 — Cookie import

- Support cookie JSON exports and Netscape cookies.txt.
- Store cookie jar locally (ignored by git).

### FR2 — Auth check

- Verify access to `/my/`.
- Detect login page reliably.

### FR3 — Course discovery

- Extract course IDs and titles from `/my/`.

### FR4 — Sync course structure

- Extract sections and items from `course/view.php`.
- Identify items by activity id when available; otherwise use URL.

### FR5 — Deadline enrichment (best-effort)

- For assignments/quizzes, parse due/close times from activity pages.
- Handle English and Vietnamese labels.

### FR6 — Snapshot storage

- Write stable, deterministic JSON output.

### FR7 — Diff engine

- Compare last snapshot to new snapshot.
- Emit a minimal set of human-actionable events.

### FR8 — Notifications

- Send events to one channel (Telegram or Discord) with clear formatting.
- Send “auth expired” as high priority.

### FR9 — Export into main repo

- Write to a configured local path.
- Avoid deleting user files.

## 12) Non-functional requirements

- **Reliability:** Should not silently fail. Any auth failure must surface via event/notification.
- **Performance:** Sync should complete within minutes for typical course loads (local runs).
- **Safety:** Cookie jar and secrets must never be committed.
- **Maintainability:** Parsing logic must be modular and testable with fixtures.
- **Observability:** Structured logs (`tracing`) + debug mode.

## 13) Security, privacy, and secrets

- Treat cookies as secrets. Store under `.cache/` and ensure it is ignored by git.
- Do not store LMS passwords long-term; prefer cookie import.
- Never scrape or export personally sensitive data beyond what the user’s account can see and needs.

## 14) MVP roadmap (phased milestones)

### Milestone 0 — Project setup (Rust workspace)

- Create Rust crate(s) with `clap`, `tokio`, `reqwest`, `serde`, `tracing`.
- Add config parsing from `.env` / env vars.

### Milestone 1 — Auth & cookie jar

- Implement `import-cookies` and `auth-check`.
- Store cookie jar on disk.

### Milestone 2 — Course discovery

- Implement `/my/` parser and `courses` command.

### Milestone 3 — Sync & normalize

- Implement course page parser and JSON snapshot outputs.

### Milestone 4 — Diff & events

- Implement diff engine and event outputs.

### Milestone 5 — Notifications

- Implement Telegram or Discord notifier.
- Add `watch` scheduler.

### Milestone 6 — Export into main repo

- Implement exporter with deterministic file layout.
- Optional: `--git-commit` (later).

## 15) Acceptance criteria (MVP)

- AC1: `auth-check` succeeds using imported cookies.
- AC2: `courses` lists at least one course id/title.
- AC3: `sync --all` writes snapshots to the configured output.
- AC4: Modifying a course item (teacher changes title/deadline) produces an event on next sync.
- AC5: Notifications arrive on phone/desktop within the watch interval.
- AC6: Exporter writes into the user’s main repo path without manual copying.
- AC7: Exporter writes both JSON snapshots and a minimal Markdown index.

## 16) Risks and mitigations

| Risk                        |  Impact | Mitigation                                                                              |
| --------------------------- | ------: | --------------------------------------------------------------------------------------- |
| SSO changes / cookie expiry |    High | Cookie import workflow + “auth expired” notifications; optional headless browser later. |
| Moodle HTML changes         |  Medium | Parser modularity + fixtures + fast iteration.                                          |
| Rate limiting / anti-bot    |  Medium | Low concurrency, backoff, respectful intervals.                                         |
| Deadlines not parseable     |  Medium | Always store `due_raw`; provide `--with-deadlines` as best effort.                      |
| Export repo conflicts       | Low/Med | Write into a dedicated subdir; avoid destructive operations.                            |

## 17) Final decisions (locked)

1. **Notifications:** Telegram (MVP).
2. **Main repo export path:** `C:\Users\minhc\Code\Personal-Knowledge-Vault` (base repo).
3. **Sync runtime:** local computer, scheduled at startup + interval (Windows Task Scheduler). Optional always-on server later.
4. **Export format:** JSON snapshots + minimal Markdown index.
5. **Default watch interval:** 15 minutes.

## 18) Appendix — Configuration (proposed env vars)

- `MOODLE_BASE_URL=https://lms.hcmut.edu.vn`
- `COOKIE_JAR_PATH=.cache/cookies.json`
- `DATA_DIR=./data` (internal outputs)
- `EXPORT_REPO_PATH=C:\\Users\\minhc\\Code\\Personal-Knowledge-Vault`
- `EXPORT_SUBDIR=lms`
- `WATCH_INTERVAL=15m`
- Notification (choose one):
  - Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
  - Discord: `DISCORD_WEBHOOK_URL`

## 19) Appendix — Learning outcomes (Rust backend)

By building this MVP you will practice:

- Async HTTP clients (`reqwest` + cookies)
- Robust HTML parsing and normalization
- Designing stable schemas and diff/event systems
- CLI ergonomics (`clap`) and observability (`tracing`)
- Building a production-ish background job (`watch`)

---

**Next action:** start Milestone 0 (Rust workspace scaffold + config + logging) and commit the first runnable CLI (`--help`).
