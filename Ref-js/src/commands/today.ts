import { Command } from 'commander';

import { loadConfig } from '../config';
import { loadAllCourses } from '../store/jsonStore';

type DueItem = {
  courseId: number;
  courseTitle: string;
  sectionTitle: string;
  title: string;
  url: string;
  dueAt?: string;
  dueRaw?: string;
};

export const todayCommand = new Command('today')
  .description('Show what is due soon based on normalized metadata')
  .option('--days <n>', 'Lookahead window in days', '7')
  .action(async (opts: { days: string }) => {
    const config = loadConfig();
    const days = Math.max(1, Number(opts.days) || 7);
    const courses = await loadAllCourses(config.dataDir);
    if (courses.length === 0) {
      // eslint-disable-next-line no-console
      console.log('No synced courses found. Run `npm run sync` first.');
      return;
    }

    const now = Date.now();
    const horizon = now + days * 24 * 60 * 60 * 1000;

    const due: DueItem[] = [];
    const unknown: DueItem[] = [];

    for (const course of courses) {
      for (const section of course.sections) {
        for (const item of section.items) {
          if (!(item.kind === 'assignment' || item.kind === 'quiz')) continue;
          const base: DueItem = {
            courseId: course.source.courseId,
            courseTitle: course.title,
            sectionTitle: section.title,
            title: item.title,
            url: item.url,
            dueAt: item.dueAt,
            dueRaw: item.dueRaw
          };

          if (!item.dueAt) {
            unknown.push(base);
            continue;
          }
          const t = new Date(item.dueAt).getTime();
          if (!Number.isFinite(t)) {
            unknown.push(base);
            continue;
          }
          if (t >= now && t <= horizon) due.push(base);
        }
      }
    }

    due.sort(
      (a, b) => new Date(a.dueAt ?? 0).getTime() - new Date(b.dueAt ?? 0).getTime()
    );

    if (due.length === 0) {
      // eslint-disable-next-line no-console
      console.log(`No due items found in the next ${days} day(s).`);
    } else {
      // eslint-disable-next-line no-console
      console.log(`Due in the next ${days} day(s):`);
      for (const d of due) {
        // eslint-disable-next-line no-console
        console.log(`- ${d.dueAt}\t${d.courseTitle}\t${d.title}`);
      }
    }

    if (unknown.length > 0) {
      // eslint-disable-next-line no-console
      console.log('');
      // eslint-disable-next-line no-console
      console.log('Assignments/quizzes with no parsed due date (try --with-deadlines on sync):');
      for (const u of unknown.slice(0, 50)) {
        // eslint-disable-next-line no-console
        console.log(`- (no due)\t${u.courseTitle}\t${u.title}`);
      }
      if (unknown.length > 50) {
        // eslint-disable-next-line no-console
        console.log(`... and ${unknown.length - 50} more`);
      }
    }
  });
