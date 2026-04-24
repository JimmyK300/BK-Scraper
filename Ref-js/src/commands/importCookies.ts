import { Command } from 'commander';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { Cookie, CookieJar } from 'tough-cookie';

import { loadConfig } from '../config';
import { saveCookieJar } from '../moodle/cookieJar';

type CookieInput = {
  name: string;
  value: string;
  domain: string;
  path?: string;
  expires?: number | null; // seconds since epoch
  secure?: boolean;
  httpOnly?: boolean;
};

function normalizeDomain(domain: string): string {
  const d = domain.trim();
  if (!d) return d;
  // tough-cookie accepts leading dots, but normalize whitespace and case
  return d.toLowerCase();
}

function parseNetscapeCookiesTxt(text: string): CookieInput[] {
  // Format: domain\tflag\tpath\tsecure\texpiration\tname\tvalue
  const out: CookieInput[] = [];
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const parts = trimmed.split(/\t/);
    if (parts.length < 7) continue;
    const [domain, _flag, cookiePath, secureRaw, expRaw, name, value] = parts;
    const expires = Number(expRaw);
    out.push({
      name,
      value,
      domain,
      path: cookiePath,
      expires: Number.isFinite(expires) ? expires : null,
      secure: secureRaw.toUpperCase() === 'TRUE'
    });
  }
  return out;
}

function parseCookieJsonAuto(json: unknown): CookieInput[] {
  // Supported:
  // 1) Playwright storage state: { cookies: [...] }
  // 2) Chrome/extension export: [ ...cookies ]
  if (typeof json !== 'object' || json === null) throw new Error('Invalid JSON cookie file.');

  const asAny = json as any;
  const list: any[] = Array.isArray(asAny) ? asAny : Array.isArray(asAny.cookies) ? asAny.cookies : [];
  if (!Array.isArray(list)) throw new Error('Unrecognized cookie JSON format.');

  const out: CookieInput[] = [];
  for (const c of list) {
    if (!c) continue;
    const name = String(c.name ?? '');
    const value = String(c.value ?? '');
    const domain = String(c.domain ?? c.host ?? '');
    if (!name || !domain) continue;

    const expiresNum =
      typeof c.expires === 'number'
        ? c.expires
        : typeof c.expirationDate === 'number'
          ? c.expirationDate
          : null;

    out.push({
      name,
      value,
      domain,
      path: typeof c.path === 'string' ? c.path : '/',
      expires: expiresNum,
      secure: Boolean(c.secure),
      httpOnly: Boolean(c.httpOnly)
    });
  }

  return out;
}

function toSetCookieUrl(input: CookieInput): string {
  const domain = normalizeDomain(input.domain).replace(/^\./, '');
  const scheme = input.secure ? 'https' : 'http';
  return `${scheme}://${domain}/`;
}

export const importCookiesCommand = new Command('import-cookies')
  .description('Import browser-exported cookies into the tough-cookie jar used by the scraper')
  .argument('<file>', 'Path to cookies JSON (Playwright/Chrome export) or Netscape cookies.txt')
  .option('--out <path>', 'Output jar path (defaults to MOODLE_COOKIE_JAR_PATH)')
  .option(
    '--format <format>',
    'Input format: auto | json | netscape',
    'auto'
  )
  .action(async (file: string, opts: { out?: string; format?: string }) => {
    const config = loadConfig();
    const outPath = opts.out ?? config.cookieJarPath;
    const format = (opts.format ?? 'auto').toLowerCase();

    const raw = await readFile(file, 'utf-8');

    let cookies: CookieInput[] = [];
    if (format === 'netscape') {
      cookies = parseNetscapeCookiesTxt(raw);
    } else if (format === 'json') {
      cookies = parseCookieJsonAuto(JSON.parse(raw));
    } else {
      // auto
      const ext = path.extname(file).toLowerCase();
      if (ext === '.txt' || raw.startsWith('# Netscape HTTP Cookie File')) {
        cookies = parseNetscapeCookiesTxt(raw);
      } else {
        cookies = parseCookieJsonAuto(JSON.parse(raw));
      }
    }

    if (cookies.length === 0) {
      throw new Error('No cookies parsed from file.');
    }

    const jar = new CookieJar();
    for (const c of cookies) {
      const cookie = new Cookie({
        key: c.name,
        value: c.value,
        domain: normalizeDomain(c.domain),
        path: c.path ?? '/',
        expires: c.expires ? new Date(c.expires * 1000) : 'Infinity',
        secure: Boolean(c.secure),
        httpOnly: Boolean(c.httpOnly)
      });
      // Use a URL that matches the cookie's domain so tough-cookie accepts it.
      jar.setCookieSync(cookie, toSetCookieUrl(c), { ignoreError: true });
    }

    await saveCookieJar(outPath, jar);

    // eslint-disable-next-line no-console
    console.log(`Imported ${cookies.length} cookie(s) -> ${outPath}`);
    // eslint-disable-next-line no-console
    console.log('Now run: npm run courses');
  });
