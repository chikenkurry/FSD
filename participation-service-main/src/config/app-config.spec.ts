import { AppConfig } from './app-config';

const KEYS = [
  'NODE_ENV',
  'PORT',
  'AUTH_MODE',
  'INTERNAL_API_TOKEN',
  'PLANNING_BASE_URL',
  'SESSION_COOKIE_NAME',
] as const;

describe('AppConfig', () => {
  const saved: Record<string, string | undefined> = {};

  beforeEach(() => {
    for (const key of KEYS) saved[key] = process.env[key];
    for (const key of KEYS) delete process.env[key];
    process.env.INTERNAL_API_TOKEN = 'a-long-enough-secret';
    process.env.AUTH_MODE = 'dev';
  });

  afterEach(() => {
    for (const key of KEYS) {
      if (saved[key] === undefined) delete process.env[key];
      else process.env[key] = saved[key];
    }
  });

  it('applies defaults', () => {
    const config = new AppConfig();
    expect(config).toMatchObject({
      nodeEnv: 'development',
      port: 3000,
      authMode: 'dev',
      sessionCookieName: 'what2do_session',
    });
  });

  it('refuses dev auth in production', () => {
    process.env.NODE_ENV = 'production';
    expect(() => new AppConfig()).toThrow(/AUTH_MODE=dev/);
  });

  it('requires a long enough internal token', () => {
    process.env.INTERNAL_API_TOKEN = 'short';
    expect(() => new AppConfig()).toThrow(/INTERNAL_API_TOKEN/);
  });

  it('requires the Planning URL when authorising through Planning', () => {
    process.env.AUTH_MODE = 'planning';
    expect(() => new AppConfig()).toThrow(/PLANNING_BASE_URL/);
    process.env.PLANNING_BASE_URL = 'http://planning:3001/';
    expect(new AppConfig().planningBaseUrl).toBe('http://planning:3001');
  });

  it('rejects an unknown auth mode and a bad port', () => {
    process.env.AUTH_MODE = 'magic';
    expect(() => new AppConfig()).toThrow(/AUTH_MODE/);
    process.env.AUTH_MODE = 'dev';
    process.env.PORT = 'abc';
    expect(() => new AppConfig()).toThrow(/PORT/);
  });
});
