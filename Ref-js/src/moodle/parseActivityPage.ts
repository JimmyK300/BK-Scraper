import * as cheerio from 'cheerio';
import type { AnyNode } from 'domhandler';

export type DeadlineInfo = {
  dueAt?: string;
  dueRaw?: string;
};

const ASSIGN_LABELS = [/\bdue\s*date\b/i, /\bdue\b/i, /hạn\s*nộp/i, /ngày\s*hết\s*hạn/i];
const QUIZ_LABELS = [/\btime\s*closes\b/i, /\bclose\b/i, /đóng/i, /kết\s*thúc/i];

function extractTimeIso($row: cheerio.Cheerio<AnyNode>): DeadlineInfo {
  const time = $row.find('time[datetime]').first();
  const dt = time.attr('datetime');
  if (dt) {
    const iso = new Date(dt).toISOString();
    const dueRaw = time.text().replace(/\s+/g, ' ').trim() || dt;
    return { dueAt: iso, dueRaw };
  }

  const text = $row.text().replace(/\s+/g, ' ').trim();
  return text ? { dueRaw: text } : {};
}

function rowLabelMatches(label: string, patterns: RegExp[]): boolean {
  const normalized = label.replace(/\s+/g, ' ').trim();
  return patterns.some((p) => p.test(normalized));
}

export function extractDeadlineFromActivityPage(options: {
  html: string;
  modType?: string;
}): DeadlineInfo {
  const $ = cheerio.load(options.html);
  const patterns = options.modType === 'quiz' ? QUIZ_LABELS : ASSIGN_LABELS;

  // Common Moodle layout: a table with th/td rows (e.g., Assignment info)
  const rows = $('table tr');
  for (const row of rows.toArray()) {
    const $row = $(row);
    const label = $row.find('th').first().text();
    if (!label) continue;
    if (!rowLabelMatches(label, patterns)) continue;

    const cell = $row.find('td').first();
    const info = extractTimeIso(cell.length ? cell : $row);
    if (info.dueAt || info.dueRaw) return info;
  }

  // Fallback: look for any time elements on the page
  const anyTime = $('time[datetime]').last();
  const dt = anyTime.attr('datetime');
  if (dt) {
    return {
      dueAt: new Date(dt).toISOString(),
      dueRaw: anyTime.text().replace(/\s+/g, ' ').trim() || dt
    };
  }

  return {};
}
