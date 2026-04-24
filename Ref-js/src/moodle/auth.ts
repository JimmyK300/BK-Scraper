import { AxiosInstance } from 'axios';
import { CookieJar } from 'tough-cookie';
import * as cheerio from 'cheerio';

import { AppConfig } from '../config';
import { createMoodleHttpClient } from './client';
import { loadCookieJar, saveCookieJar } from './cookieJar';

function looksLikeLoginPage(html: string): boolean {
  const $ = cheerio.load(html);
  const hasUsername = $('input[name="username"]').length > 0;
  const hasPassword = $('input[name="password"]').length > 0;
  const hasLoginToken = $('input[name="logintoken"]').length > 0;
  return hasUsername && hasPassword && hasLoginToken;
}

async function isLoggedIn(client: AxiosInstance): Promise<boolean> {
  const res = await client.get('/my/');
  const html = String(res.data ?? '');

  if (looksLikeLoginPage(html)) return false;
  if (html.includes('/login/logout.php')) return true;
  if (html.toLowerCase().includes('logout')) return true;

  // Fallback: if we can hit /my/ and it doesn't look like the login form, assume session is OK.
  return true;
}

async function loginWithPassword(client: AxiosInstance, config: AppConfig): Promise<void> {
  if (!config.moodleUsername || !config.moodlePassword) {
    throw new Error('Missing MOODLE_USERNAME/MOODLE_PASSWORD');
  }

  const loginPage = await client.get('/login/index.php');
  const $ = cheerio.load(String(loginPage.data ?? ''));
  const logintoken = $('input[name="logintoken"]').attr('value');
  if (!logintoken) {
    throw new Error(
      'Could not find Moodle logintoken on /login/index.php (SSO/CAS/OAuth may be enabled).'
    );
  }

  const form = new URLSearchParams();
  form.set('logintoken', logintoken);
  form.set('username', config.moodleUsername);
  form.set('password', config.moodlePassword);

  await client.post('/login/index.php', form, {
    headers: {
      'content-type': 'application/x-www-form-urlencoded'
    }
  });

  const ok = await isLoggedIn(client);
  if (!ok) {
    throw new Error(
      'Login failed (credentials rejected or login flow is not the standard Moodle form).'
    );
  }
}

export async function createAuthenticatedMoodleClient(config: AppConfig): Promise<{
  client: AxiosInstance;
  cookieJar: CookieJar;
}> {
  const jar = (await loadCookieJar(config.cookieJarPath)) ?? new CookieJar();
  const client = createMoodleHttpClient({
    baseUrl: config.moodleBaseUrl,
    cookieJar: jar,
    userAgent: config.userAgent
  });

  const alreadyLoggedIn = await isLoggedIn(client);
  if (!alreadyLoggedIn) {
    if (config.moodleUsername && config.moodlePassword) {
      await loginWithPassword(client, config);
    } else {
      throw new Error(
        'Not logged in and no credentials provided. Set MOODLE_USERNAME/MOODLE_PASSWORD or provide a valid cookie jar.'
      );
    }
  }

  await saveCookieJar(config.cookieJarPath, jar);
  return { client, cookieJar: jar };
}

