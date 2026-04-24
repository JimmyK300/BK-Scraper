import { Command } from 'commander';

import { listCoursesCommand } from './commands/courses';
import { importCookiesCommand } from './commands/importCookies';
import { listAssignmentsCommand } from './commands/listAssignments';
import { syncCommand } from './commands/sync';
import { todayCommand } from './commands/today';

const program = new Command();

program
  .name('bkscraper')
  .description('Moodle ingestion + normalization CLI')
  .version('0.1.0');

program.addCommand(syncCommand);
program.addCommand(todayCommand);
program.addCommand(listAssignmentsCommand);
program.addCommand(listCoursesCommand);
program.addCommand(importCookiesCommand);

program.parseAsync(process.argv).catch((err: unknown) => {
  const message = err instanceof Error ? err.message : String(err);
  // eslint-disable-next-line no-console
  console.error(message);
  process.exitCode = 1;
});

