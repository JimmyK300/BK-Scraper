import path from 'node:path';
import { readdir } from 'node:fs/promises';
import { NormalizedCourse, NormalizedCourseSchema } from '../normalize/types';
import { ensureDir, readJsonFile, writeJsonFile } from '../utils/fs';

export type CourseIndexEntry = {
  courseId: number;
  title: string;
  lastSyncedAt: string;
};

export type CourseIndex = {
  baseUrl: string;
  courses: CourseIndexEntry[];
};

export async function saveCourse(dataDir: string, course: NormalizedCourse): Promise<void> {
  const coursePath = path.join(dataDir, 'courses', `${course.source.courseId}.json`);
  await writeJsonFile(coursePath, course);

  const indexPath = path.join(dataDir, 'index.json');
  const nextEntry: CourseIndexEntry = {
    courseId: course.source.courseId,
    title: course.title,
    lastSyncedAt: course.source.scrapedAt
  };

  let index: CourseIndex = { baseUrl: course.source.baseUrl, courses: [] };
  try {
    index = await readJsonFile<CourseIndex>(indexPath);
  } catch {
    // ignore missing index
  }

  index.baseUrl = course.source.baseUrl;
  const existing = index.courses.findIndex((c) => c.courseId === nextEntry.courseId);
  if (existing >= 0) index.courses[existing] = nextEntry;
  else index.courses.push(nextEntry);

  index.courses.sort((a, b) => a.courseId - b.courseId);
  await writeJsonFile(indexPath, index);
}

export async function loadAllCourses(dataDir: string): Promise<NormalizedCourse[]> {
  const coursesDir = path.join(dataDir, 'courses');
  await ensureDir(coursesDir);
  const files = await readdir(coursesDir);

  const courses: NormalizedCourse[] = [];
  for (const file of files) {
    if (!file.endsWith('.json')) continue;
    const full = path.join(coursesDir, file);
    const json = await readJsonFile<unknown>(full);
    const parsed = NormalizedCourseSchema.safeParse(json);
    if (parsed.success) courses.push(parsed.data);
  }
  return courses;
}
