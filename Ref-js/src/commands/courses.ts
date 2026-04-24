import { Command } from 'commander';

import { loadConfig } from '../config';
import { createAuthenticatedMoodleClient } from '../moodle/auth';
import { parseCoursesFromMyPage } from '../moodle/parseMyHome';

export const listCoursesCommand = new Command('courses')
  .description('List courses visible on Moodle /my/')
  .action(async () => {
    const config = loadConfig();
    const { client } = await createAuthenticatedMoodleClient(config);

    const res = await client.get('/my/');
    const courses = parseCoursesFromMyPage(config.moodleBaseUrl, String(res.data ?? ''));

    if (courses.length === 0) {
      // eslint-disable-next-line no-console
      console.log('No courses found on /my/.');
      return;
    }

    for (const c of courses) {
      // eslint-disable-next-line no-console
      console.log(`${c.courseId}\t${c.title}`);
    }
  });
