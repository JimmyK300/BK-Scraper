# BKScraper

Pipeline-first Moodle ingestion with a tiny CLI.

This is intentionally **not** an “AI app” yet — it focuses on the hard part first:

1) reliably authenticating + crawling Moodle, then
2) normalizing content into a clean schema you can query later.

## Safety / policy

Only use this against accounts/courses you have explicit permission to access, and in ways that comply with your school’s LMS policies.

## Setup

1. Install deps

```bash
npm install
```

2. Create `.env`

```bash
copy .env.example .env
```

3. Fill in at least:

- `MOODLE_BASE_URL`
- `MOODLE_USERNAME` / `MOODLE_PASSWORD` (or provide a cookie jar file manually)

## Commands

### List courses (from `/my/`)

```bash
npm run courses
```

### If your Moodle uses SSO (cookie import)

If username/password login fails (e.g., SSO / CAS / OAuth), you can:

1) Log in via your browser
2) Export cookies (JSON or Netscape cookies.txt)
3) Import them into the scraper jar:

```bash
npm run dev -- import-cookies path\\to\\cookies.json
```

Then try `npm run courses` again.

### Sync

Sync specific courses:

```bash
npm run sync -- --course 123 --course 456
```

Or sync all courses visible on `/my/`:

```bash
npm run sync -- --all
```

Optional: try to enrich deadlines by visiting each assignment/quiz page:

```bash
npm run sync -- --all --with-deadlines
```

### What’s due soon

```bash
npm run today -- --days 7
```

### List assignments

```bash
npm run list:assignments
```

## Output

- Normalized course JSON is written to `data/courses/<courseId>.json`
- An index is written to `data/index.json`

## Next steps (planned)

- Add content extraction (PDF/HTML → text)
- Add a Postgres metadata store (keep JSON as fallback)
- Add an action-focused “planner” command (today/this-week/behind)
