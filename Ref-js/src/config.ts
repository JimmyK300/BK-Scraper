import * as dotenv from 'dotenv';
import { z } from 'zod';

dotenv.config();

const ConfigSchema = z.object({
  moodleBaseUrl: z
    .string()
    .url()
    .transform((s) => s.replace(/\/+$/, '')),
  moodleUsername: z.string().optional(),
  moodlePassword: z.string().optional(),
  cookieJarPath: z.string().default('.cache/moodle-cookiejar.json'),
  dataDir: z.string().default('data'),
  requestConcurrency: z.coerce.number().int().min(1).max(32).default(4),
  userAgent: z.string().default('BKScraper/0.1 (+local)'),
  defaultCourseIds: z
    .string()
    .optional()
    .transform((v) => {
      if (!v) return [] as number[];
      return v
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map((s) => Number(s))
        .filter((n) => Number.isFinite(n));
    })
});

export type AppConfig = z.infer<typeof ConfigSchema>;

export function loadConfig(): AppConfig {
  const parsed = ConfigSchema.safeParse({
    moodleBaseUrl: process.env.MOODLE_BASE_URL,
    moodleUsername: process.env.MOODLE_USERNAME,
    moodlePassword: process.env.MOODLE_PASSWORD,
    cookieJarPath: process.env.MOODLE_COOKIE_JAR_PATH,
    dataDir: process.env.DATA_DIR,
    requestConcurrency: process.env.REQUEST_CONCURRENCY,
    userAgent: process.env.USER_AGENT,
    defaultCourseIds: process.env.MOODLE_COURSE_IDS
  });

  if (!parsed.success) {
    const issues = parsed.error.issues
      .map((i) => `${i.path.join('.') || 'config'}: ${i.message}`)
      .join('\n');
    throw new Error(`Invalid configuration:\n${issues}`);
  }

  return parsed.data;
}
