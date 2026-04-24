import { Command } from 'commander';

import { loadConfig } from '../config';
import { loadAllCourses } from '../store/jsonStore';

export const listAssignmentsCommand = new Command('list-assignments')
  .description('List assignments across all synced courses')
  .action(async () => {
    const config = loadConfig();
    const courses = await loadAllCourses(config.dataDir);
    if (courses.length === 0) {
      // eslint-disable-next-line no-console
      console.log('No synced courses found. Run `npm run sync` first.');
      return;
    }

    for (const course of courses) {
      for (const section of course.sections) {
        for (const item of section.items) {
          if (item.kind !== 'assignment') continue;
          // eslint-disable-next-line no-console
          console.log(
            `${course.source.courseId}\t${course.title}\t${item.dueAt ?? ''}\t${item.title}`
          );
        }
      }
    }
  });
