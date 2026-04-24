# Learning Plan — Build the HCMUT LMS Companion (Rust Backend)

**Linked PRD:** `docs/lms-assistant-prd.md`

**Document version:** 1.0 (final)

**Date:** 2026-04-12

**Purpose:** A practical, project-driven learning plan for backend development in Rust, using this project as the “curriculum”.

---

## 0) How to use this plan (so it actually works)

This plan is designed around a simple loop:

1. **Learn just enough** (small reading / examples)
2. **Build a real slice** in the project
3. **Validate** (tests, logs, run it)
4. **Reflect + notes** (what broke, what you learned)

If a topic doesn’t unlock a project milestone, we defer it.

### Plan inputs (locked)

- **Time budget:** 21 hours/week (≈ 3 hours/day)
- **Pace:** 4 weeks
- **Environment:** Windows (local-first)
- **Learning style:** strong theory + implementation; heavy AI integration into workflow, but you still understand before copying code
- **Baseline:**
  - Rust: beginner
  - HTTP + backend concepts: intermediate
  - HTML parsing/scraping: beginner–intermediate
- **Optional tracks:** axum API server is _deferred until after MVP_ (add-on week)

### AI integration rules (workflow, not learning shortcut)

Use AI as a **reviewer + debugger + boilerplate accelerator**, not as a replacement for understanding.

**Rule 1 — “Explain first”**

- Before asking AI to write code, write a short design note (5–10 sentences): inputs/outputs, edge cases, and acceptance checks.

**Rule 2 — “Small diffs only”**

- Ask AI for small patches (≤ 1–2 files) and apply them yourself. You should always be able to explain each change.

**Rule 3 — “Tests/fixtures over live poking”**

- For parsing: save real HTML samples as fixtures and write tests.
- For network flows: keep a “dry-run” and log-driven approach.

**Rule 4 — “Failure journaling”**

- When stuck, capture:
  - the exact error message,
  - what you tried,
  - one hypothesis.
- Then ask AI to explain the likely root cause and propose a minimal fix.

**Rule 5 — “No secrets”**

- Never paste cookies/tokens/passwords into prompts.

---

## 1) Learning outcomes (what “backend Rust” means here)

By the end of MVP, you should be comfortable with:

- Building a **production-ish CLI service** (structured logs, config, error handling)
- Async Rust with **Tokio** (tasks, time intervals, concurrency limits)
- HTTP client work with **reqwest** (cookies, headers, retries)
- HTML parsing into a stable schema (scraping safely)
- Designing **data schemas** (`serde`) and writing deterministic outputs
- Implementing a **diff/event system** (change detection)
- Delivering notifications via a real integration (Telegram)
- Running on Windows reliably (Task Scheduler)

Optional “backend depth” track:

- Exposing an HTTP API with **axum**
- Moving metadata from JSON → Postgres with **sqlx** migrations

---

## 2) Setup checklist (Day 0)

### Tools

- Install Rust via `rustup` (stable toolchain) ✅
- VS Code: rust-analyzer, CodeLLDB ✅
- Ensure Windows build tools are available (MSVC) ⬜
  - Install **Visual Studio Build Tools 2022** (or full Visual Studio) and enable:
    - “Desktop development with C++”
    - Windows 10/11 SDK
  - Validation commands:
    - `rustc -V` and `cargo -V`
    - `where cl` (should find MSVC `cl.exe`)
    - `cargo new hello && cd hello && cargo build` (first compile test)

### Repo structure (recommended)

- **Repo root = Rust workspace** (this is the “real” project)
  - `Cargo.toml` (workspace)
  - `crates/`
    - `lms_cli/` (CLI binary)
    - `lms_core/` (models, parsing, diff, export)
  - `docs/` (PRD + learning plan)
  - `.cache/` (cookies + runtime cache, gitignored)
  - `data/` (snapshots + events, gitignored)
- `Ref-js/` = reference Node/TS prototype (keep for comparison only)

---

## 3) Learning roadmap (milestones aligned to PRD)

Each milestone is a “shippable slice” with a clear definition of done.

### 3.1) Week-by-week schedule (4 weeks, 21h/week)

This is the primary execution schedule. The milestone definitions below are the reference spec.

### Week 1 — Foundation + Auth (Milestone 0 + most of 1)

**Theory focus (≈ 4–5h)**

- Rust basics you’ll hit immediately: ownership/borrowing, `Result`, enums/structs, modules
- Async mental model: `async/await`, `tokio` runtime, tasks
- CLI design: subcommands/options, config validation

**Week 1 theory pack (what to read + how to find it)**

The goal of Week 1 theory is not “learn Rust”. It’s to learn exactly what you need to build:

- a CLI skeleton,
- config + logging,
- an async HTTP client,
- cookie persistence,
- and a reliable auth check.

Use these sources (in this order). For each item: read until you can explain it, then build.

1. **Core Rust (must-have)**

- The Rust Book:
  - Ownership/borrowing (Chapter 4)
  - Structs/enums + `match` (Chapters 5–6)
  - Modules/crates/workspaces (Chapter 7)
  - Error handling (`Result`, `?`, custom errors) (Chapter 9)
- Quick lookup:
  - Rust By Example: modules, error handling, structs/enums

How to search:

- `the rust programming language chapter 4 ownership`
- `the rust programming language chapter 7 packages crates modules`
- `rust error handling anyhow thiserror`

2. **Async + Tokio (must-have)**

- Tokio docs/tutorial (focus on):
  - `#[tokio::main]`
  - `tokio::spawn`
  - `tokio::time::interval`
  - cancellation / graceful shutdown basics

How to search:

- `tokio interval example`
- `tokio spawn joinhandle`

3. **CLI ergonomics (must-have)**

- clap (derive) docs:
  - subcommands
  - required/optional flags
  - default values

How to search:

- `clap derive subcommands example`

4. **Logging/observability (must-have)**

- tracing + tracing-subscriber:
  - spans vs events
  - env filter (`RUST_LOG`)
  - pretty vs json output (pretty is fine for MVP)

How to search:

- `tracing subscriber EnvFilter RUST_LOG`

5. **HTTP client + cookies (must-have)**

- reqwest basics:
  - creating a shared `Client`
  - timeouts
  - headers
  - redirects
- cookie store:
  - pick a cookie jar approach (in code) and persist it to disk

How to search:

- `reqwest cookie jar persistent`
- `reqwest cookie_store CookieStoreMutex`

**Stop rule (very important):** if the reading does not directly help you implement Milestone 0 or 1 today, stop and switch to code.

**Build focus (≈ 14–16h)**

- Create the Rust workspace structure **at the repo root** and a runnable CLI crate
- Implement:
  - config loader (env + `.env`)
  - structured logging (`tracing`)
  - command scaffolds
- Implement cookie jar import + persistence (file on disk)
- Implement `auth-check` against `/my/` with “logged in vs login page” detection

**Execution checklist (Week 1, do in order)**

**Step 1 — Get MSVC working (Windows prerequisite)**

Because you are on Windows and `cl.exe` is not currently found, you need MSVC build tools.

1. Install **Visual Studio Build Tools 2022**.
2. In the installer, select:

- Workload: **Desktop development with C++**
- Components: Windows 10/11 SDK

3. Validate in PowerShell:

- `where cl` (must print a path)
- `rustc -V` and `cargo -V`

4. Validate compilation:

- `cargo new hello && cd hello && cargo build`

If `where cl` still prints nothing, open “x64 Native Tools Command Prompt for VS 2022” once, or re-run the installer and confirm the C++ workload is installed.

**Step 2 — Initialize the Rust workspace at repo root**

- Create `Cargo.toml` (workspace)
- Create `crates/lms_cli` and `crates/lms_core`

**Step 3 — Make the CLI run**

- `cargo run -p lms_cli -- --help`
- Add `RUST_LOG=debug` and confirm logs show up

**Validation (≈ 1–2h)**

- `cargo test` and `cargo run -- --help`
- Run `auth-check` with imported cookies (no secrets logged)

**Definition of done**

- You can reliably detect “session valid” vs “session expired” locally.

### Week 2 — Course discovery + Snapshot sync (Milestone 2 + core of 3)

**Theory focus (≈ 4h)**

- HTML parsing patterns with `scraper` (selectors, text normalization)
- Designing data models with `serde` (and stable JSON output)
- IO patterns: atomic file writes, deterministic ordering

**Build focus (≈ 15h)**

- Implement `/my/` parser → `courses` command
- Implement course page parser → normalized snapshot JSON per course
- Add fixture-based tests for `/my/` and one course page

**Validation**

- `sync --all` writes snapshots deterministically
- Re-running sync without LMS changes yields identical outputs

### Week 3 — Diff/events + Deadline enrichment (Milestone 4 + optional deadlines)

**Theory focus (≈ 4h)**

- “Stable identity” and diff design (what should trigger a notification)
- Date parsing strategy: store `due_raw`, parse `due_at` best-effort
- Error handling patterns (`thiserror`/`anyhow`) and context

**Build focus (≈ 15h)**

- Implement diff engine (old snapshot vs new snapshot)
- Emit events (JSONL) for added/removed/title change/due change
- Implement optional `--with-deadlines` by visiting assignment/quiz pages
  - Parse labels in English and Vietnamese
- Expand fixture tests for due parsing

**Validation**

- You can simulate changes (fixture diffs) and see correct events.

### Week 4 — Notifications + Export + Run continuously (Milestone 5 + 6)

**Theory focus (≈ 3–4h)**

- External API integration (Telegram)
- Scheduling loops and graceful shutdown
- Windows Task Scheduler fundamentals

**Build focus (≈ 15–16h)**

- Implement Telegram notifier (send concise messages)
- Implement `watch --interval 15m`
- Implement `export` to your main repo:
  - JSON snapshots
  - events log
  - minimal Markdown index
- Add a Task Scheduler template (documented steps) to run `watch` at startup

**Definition of done**

- Teacher changes trigger a Telegram message within the interval.
- Export outputs appear in your Personal-Knowledge-Vault repo without manual copying.

### If you finish early (post-MVP add-on week)

- Axum API server (“backend depth”): `GET /today`, `GET /events`, `GET /courses`
- DB track: Postgres with `sqlx` migrations
- Auto re-auth: headless browser cookie refresh (only if feasible/policy-compliant)

### Milestone 0 — Rust CLI foundation (1–2 sessions)

**Why:** Everything else depends on a good skeleton.

**Learn**

- Cargo basics (workspace, crates)
- `clap` (subcommands, options)
- `tracing` + `tracing-subscriber` (structured logs)
- Config via env vars (`dotenvy` or `std::env`), plus validation

**Build (deliverable)**

- `lms --help` works
- Commands scaffolded: `auth-check`, `import-cookies`, `courses`, `sync`, `watch`, `today`, `export`
- `RUST_LOG=debug` gives useful output

**Definition of done**

- Can run `cargo run -p lms_cli -- --help`
- Config errors are friendly and actionable

**Mini-exercises**

- Add a `--dry-run` flag on `sync`
- Add `--data-dir` option overriding env

---

### Milestone 1 — HTTP + cookies (SSO-friendly) (2–3 sessions)

**Why:** Auth is the hard constraint; without it, everything collapses.

**Learn**

- `reqwest` client + cookie store
- Persisting cookies to disk (serialize/deserialize)
- Robust “am I logged in?” checks (detect login page)
- Retry/backoff basics + respectful rate limiting

**Build (deliverable)**

- `import-cookies <file>` imports cookies (JSON or Netscape cookies.txt)
- `auth-check` hits `/my/` and reports logged in / not logged in

**Definition of done**

- If cookies are valid: `auth-check` succeeds
- If cookies are expired: clear error + emits `auth.session_expired` event (even before notifier exists)

**Mini-exercises**

- Implement a “header injector” middleware pattern (User-Agent, Accept)
- Add a `--base-url` override for testing

---

### Milestone 2 — Parse `/my/` (course discovery) (1–2 sessions)

**Learn**

- HTML parsing in Rust (e.g., `scraper` crate)
- Selecting elements, extracting attributes, text normalization

**Build**

- `courses` prints `course_id\ttitle`

**Definition of done**

- Works on your LMS `/my/` page reliably across runs

---

### Milestone 3 — Parse course page → normalized schema (3–5 sessions)

**Learn**

- Designing stable structs + `serde` JSON
- Handling “best-effort” fields: `due_raw` vs parsed `due_at`
- Organizing parsing code: pure functions + test fixtures

**Build**

- `sync --all` writes `data/courses/<id>.json` snapshots
- Optional: `sync --with-deadlines` visits assignment/quiz pages and enriches due dates (VN + EN labels)

**Definition of done**

- Snapshot format is deterministic (stable ordering)
- Snapshot validates against your schema

**Mini-exercises**

- Add unit tests with saved HTML fixtures (no network)

---

### Milestone 4 — Diff engine → events (2–4 sessions)

**Learn**

- Hashing/keys: stable item identity (activity id else URL)
- Writing “human useful” diffs (not just JSON diff)
- Append-only event logs (JSONL)

**Build**

- Compare previous snapshot vs new snapshot
- Emit events: item added/removed/title changed/due changed

**Definition of done**

- You can force a change (edit in LMS or simulate) and get a correct event

---

### Milestone 5 — Notifications (Telegram) + watch mode (2–4 sessions)

**Learn**

- Integrating external APIs (Telegram `sendMessage`)
- Formatting concise notifications
- Scheduled loops (`tokio::time::interval`), graceful shutdown

**Build**

- `watch --interval 15m` syncs, diffs, notifies
- If auth fails: sends “Session expired — refresh cookies”

**Definition of done**

- You get notifications on your phone/desktop within the interval

---

### Milestone 6 — Export into your main repo (1–3 sessions)

**Learn**

- Filesystem writes safely (atomic write patterns)
- Deterministic Markdown generation

**Build**

- `export` writes to `EXPORT_REPO_PATH/EXPORT_SUBDIR`:
  - JSON snapshots
  - event logs
  - a minimal Markdown index (course list + links)

**Definition of done**

- You can do all studying in the main repo without manual copy

---

## 4) Learning methods (what to do each session)

For each session, follow this template:

- 10–20 min: read a focused doc section (Tokio/reqwest/scraper)
- 60–120 min: implement one small feature with a test or a runnable command
- 10 min: write a short note:
  - What did I expect?
  - What broke?
  - What fixed it?
  - What should I refactor next?

---

## 5) Project hygiene (skills that matter in real backend work)

- Error handling: prefer a single error type per crate (e.g., `thiserror`) and bubble up context (`anyhow`).
- Logging: use `tracing` spans around network calls and parsing.
- Tests: parsing should be testable offline with HTML fixtures.
- Secrets: never commit cookies/tokens; use `.env` and `.cache/`.

---

## 6) Self-assessment checkpoints

After each milestone:

- Can I explain the module boundaries and why?
- Can I run it from a clean checkout with only env vars set?
- Can I reproduce a failure and find it in logs?

---

## 7) Next step (start Week 1)

1. Finish MSVC setup + run a tiny `cargo build` test.
2. Create the Rust workspace at the repo root (`Cargo.toml` + `crates/`).
3. Implement Milestone 0 skeleton until `--help` is stable.

Once those three are done, the fastest “first real win” is Milestone 1: `import-cookies` + `auth-check`.
