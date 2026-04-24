import { access, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { CookieJar, type SerializedCookieJar } from 'tough-cookie';

async function fileExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

export async function loadCookieJar(cookieJarPath: string): Promise<CookieJar | null> {
  if (!(await fileExists(cookieJarPath))) return null;
  const raw = await readFile(cookieJarPath, 'utf-8');
  const serialized = JSON.parse(raw) as SerializedCookieJar;
  return CookieJar.deserializeSync(serialized);
}

export async function saveCookieJar(cookieJarPath: string, jar: CookieJar): Promise<void> {
  await mkdir(path.dirname(cookieJarPath), { recursive: true });
  const serialized = jar.serializeSync();
  await writeFile(cookieJarPath, JSON.stringify(serialized, null, 2) + '\n', 'utf-8');
}
