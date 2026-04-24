import * as cheerio from 'cheerio';

export type MoodleCourseLink = {
  courseId: number;
  title: string;
  url: string;
};

const COURSE_ID_RE = /\/course\/view\.php\?id=(\d+)/;

export function parseCoursesFromMyPage(baseUrl: string, html: string): MoodleCourseLink[] {
  const $ = cheerio.load(html);
  const links = new Map<number, MoodleCourseLink>();

  $('a[href*="/course/view.php?id="]').each((_i, el) => {
    const href = $(el).attr('href');
    if (!href) return;
    const m = href.match(COURSE_ID_RE);
    if (!m) return;
    const courseId = Number(m[1]);
    if (!Number.isFinite(courseId)) return;

    const title = $(el).text().replace(/\s+/g, ' ').trim();
    if (!title) return;
    const url = new URL(href, baseUrl).toString();
    links.set(courseId, { courseId, title, url });
  });

  return [...links.values()].sort((a, b) => a.courseId - b.courseId);
}
