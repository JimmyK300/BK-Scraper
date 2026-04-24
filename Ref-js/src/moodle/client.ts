import axios, { AxiosInstance } from 'axios';
import { wrapper } from 'axios-cookiejar-support';
import { CookieJar } from 'tough-cookie';

export function createMoodleHttpClient(options: {
  baseUrl: string;
  cookieJar: CookieJar;
  userAgent: string;
}): AxiosInstance {
  const instance = axios.create({
    baseURL: options.baseUrl,
    withCredentials: true,
    // axios-cookiejar-support extends axios config with `jar`
    jar: options.cookieJar,
    headers: {
      'user-agent': options.userAgent,
      accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    },
    timeout: 60_000,
    validateStatus: (status) => status >= 200 && status < 400
  });

  return wrapper(instance);
}
