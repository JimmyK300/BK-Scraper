import * as cheerio from 'cheerio';
import type { AnyNode } from 'domhandler';
import { ItemKind, NormalizedCourse, NormalizedCourseSchema, NormalizedItem } from '../normalize/types';

function pickCourseTitle($: cheerio.CheerioAPI): string {
  const title = $('h1').first().text().replace(/\s+/g, ' ').trim();
  if (title) return title;
  const t2 = $('title').first().text().replace(/\s+/g, ' ').trim();
  return t2 || 'Untitled course';
}

function detectModType(classAttr: string | undefined): string | undefined {
  if (!classAttr) return undefined;
  const match = classAttr.match(/\bmodtype_([a-zA-Z0-9_]+)\b/);
  return match?.[1];
}

function mapKind(modType: string | undefined): ItemKind {
  switch (modType) {
    case 'assign':
      return 'assignment';
    case 'quiz':
      return 'quiz';
    case 'forum':
      return 'notes';
    case 'resource':
    case 'page':
    case 'url':
    case 'folder':
      return 'lecture';
    default:
      return 'unknown';
  }
}

function parseActivityId(idAttr: string | undefined, dataActivityId: string | undefined): number | undefined {
  const fromData = dataActivityId ? Number(dataActivityId) : NaN;
  if (Number.isFinite(fromData)) return fromData;

  if (!idAttr) return undefined;
  const m = idAttr.match(/(module|activity)-(\d+)/);
  if (!m) return undefined;
  const n = Number(m[2]);
  return Number.isFinite(n) ? n : undefined;
}

function parseInlineDueDate($li: cheerio.Cheerio<AnyNode>): { dueAt?: string; dueRaw?: string } {
  const timeEl = $li.find('time[datetime]').last();
  const dt = timeEl.attr('datetime');
  if (dt) {
    const iso = new Date(dt).toISOString();
    return { dueAt: iso, dueRaw: timeEl.text().replace(/\s+/g, ' ').trim() || dt };
  }
  const text = $li.find('.activity-dates, .activitydates, .activity-date, .activitydate').text();
  const dueRaw = text.replace(/\s+/g, ' ').trim();
  if (dueRaw) return { dueRaw };
  return {};
}

export function parseCoursePage(options: {
  baseUrl: string;
  courseId: number;
  html: string;
}): NormalizedCourse {
  const $ = cheerio.load(options.html);
  const title = pickCourseTitle($);

  const sections: NormalizedCourse['sections'] = [];

  const sectionEls = $('.course-content').find('li.section');
  const effectiveSectionEls = sectionEls.length > 0 ? sectionEls : $('li.section');

  effectiveSectionEls.each((_i, el) => {
    const $section = $(el);
    const sectionId = $section.attr('id');
    const sectionIndexMatch = sectionId?.match(/section-(\d+)/);
    const sectionIndex = sectionIndexMatch ? Number(sectionIndexMatch[1]) : undefined;

    const sectionTitle =
      $section
        .find('.sectionname')
        .first()
        .text()
        .replace(/\s+/g, ' ')
        .trim() ||
      (Number.isFinite(sectionIndex) ? `Section ${sectionIndex}` : 'Section');

    const items: NormalizedItem[] = [];

    $section.find('li.activity').each((_j, li) => {
      const $li = $(li);
      const href =
        $li.find('a.aalink').first().attr('href') ??
        $li.find('.activityname a').first().attr('href') ??
        $li.find('a').first().attr('href');
      if (!href) return;

      const url = new URL(href, options.baseUrl).toString();
      const modType = detectModType($li.attr('class'));
      const kind = mapKind(modType);

      const nameNode = $li.find('.instancename').first();
      const nameClean = nameNode
        .clone()
        .find('span.accesshide')
        .remove()
        .end()
        .text()
        .replace(/\s+/g, ' ')
        .trim();
      const title = nameClean || $li.text().replace(/\s+/g, ' ').trim();
      if (!title) return;

      const activityId = parseActivityId($li.attr('id'), $li.attr('data-activityid'));
      const { dueAt, dueRaw } = parseInlineDueDate($li);

      items.push({
        source: { activityId, modType, url },
        title,
        kind,
        url,
        ...(dueAt ? { dueAt } : {}),
        ...(dueRaw ? { dueRaw } : {})
      });
    });

    if (items.length === 0 && !sectionTitle) return;

    sections.push({
      source: {
        sectionId,
        ...(Number.isFinite(sectionIndex) ? { sectionIndex } : {})
      },
      title: sectionTitle,
      items
    });
  });

  const course: NormalizedCourse = {
    source: {
      baseUrl: options.baseUrl,
      courseId: options.courseId,
      scrapedAt: new Date().toISOString()
    },
    title,
    sections
  };

  const parsed = NormalizedCourseSchema.safeParse(course);
  if (!parsed.success) {
    throw new Error('Failed to normalize course page into schema.');
  }

  return parsed.data;
}
