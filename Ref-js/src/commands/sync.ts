import { Command } from 'commander';
import { AxiosInstance } from 'axios';

import { loadConfig } from '../config';
import { createAuthenticatedMoodleClient } from '../moodle/auth';
import { extractDeadlineFromActivityPage } from '../moodle/parseActivityPage';
import { parseCoursePage } from '../moodle/parseCoursePage';
import { parseCoursesFromMyPage } from '../moodle/parseMyHome';
import { NormalizedCourse } from '../normalize/types';
import { saveCourse } from '../store/jsonStore';

function parseCourseIds(values: string[]): number[] {
  const ids = values
    .flatMap((v) => v.split(','))
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => Number(s))
    .filter((n) => Number.isFinite(n));
  return [...new Set(ids)].sort((a, b) => a - b);
}

async function enrichDeadlines(client: AxiosInstance, course: NormalizedCourse): Promise<NormalizedCourse> {
  for (const section of course.sections) {
    for (const item of section.items) {
      if (!(item.kind === 'assignment' || item.kind === 'quiz')) continue;
      const res = await client.get(item.url);
      const info = extractDeadlineFromActivityPage({
        html: String(res.data ?? ''),
        modType: item.source.modType
      });
      if (info.dueAt) item.dueAt = info.dueAt;
      if (info.dueRaw) item.dueRaw = info.dueRaw;
    }
  }
  return course;
}

export const syncCommand = new Command('sync')
  .description('Sync Moodle courses into normalized JSON')
  .option(
    '-c, --course <id>',
    'Course ID to sync (repeatable or comma-separated)',
    (v, p: string[]) => {
      p.push(v);
      return p;
    },
    []
  )
  .option('--all', 'Sync all courses found on /my/')
  .option('--with-deadlines', 'Visit assignment/quiz pages to enrich due dates')
  .action(async (opts: { course: string[]; all?: boolean; withDeadlines?: boolean }) => {
    const config = loadConfig();
    const { client } = await createAuthenticatedMoodleClient(config);

    let courseIds: number[] = [];
    if (opts.all) {
      const res = await client.get('/my/');
      const courses = parseCoursesFromMyPage(config.moodleBaseUrl, String(res.data ?? ''));
      courseIds = courses.map((c) => c.courseId);
    } else {
      courseIds = parseCourseIds(opts.course);
      if (courseIds.length === 0) courseIds = config.defaultCourseIds;
    }

    if (courseIds.length === 0) {
      throw new Error(
        'No course IDs provided. Use --course <id> or --all (or set MOODLE_COURSE_IDS).'
      );
    }

    for (const courseId of courseIds) {
      const res = await client.get(`/course/view.php?id=${courseId}`);
      const course = parseCoursePage({
        baseUrl: config.moodleBaseUrl,
        courseId,
        html: String(res.data ?? '')
      });

      const enriched = opts.withDeadlines ? await enrichDeadlines(client, course) : course;
      await saveCourse(config.dataDir, enriched);

      // eslint-disable-next-line no-console
      console.log(`Synced course ${courseId}: ${enriched.title}`);
    }
  });
