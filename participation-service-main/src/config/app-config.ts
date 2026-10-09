import { Injectable } from '@nestjs/common';

export type AuthMode = 'dev' | 'planning';

/** Reads and validates environment configuration once at startup, so bad config fails fast. */
@Injectable()
export class AppConfig {
  readonly nodeEnv: string;
  readonly port: number;
  readonly authMode: AuthMode;
  readonly internalApiToken: string;
  readonly planningBaseUrl: string | undefined;
  readonly sessionCookieName: string;

  constructor() {
    const env = process.env;
    this.nodeEnv = env.NODE_ENV ?? 'development';
    this.port = Number(env.PORT ?? 3000);
    this.sessionCookieName = env.SESSION_COOKIE_NAME ?? 'what2do_session';
    this.planningBaseUrl = env.PLANNING_BASE_URL?.replace(/\/+$/, '');
    this.internalApiToken = env.INTERNAL_API_TOKEN ?? '';

    const mode = env.AUTH_MODE ?? 'planning';
    if (mode !== 'dev' && mode !== 'planning') {
      throw new Error(`AUTH_MODE must be "dev" or "planning", got "${mode}"`);
    }
    this.authMode = mode;

    if (this.nodeEnv === 'production' && this.authMode === 'dev') {
      throw new Error('AUTH_MODE=dev is not allowed when NODE_ENV=production');
    }
    if (this.internalApiToken.length < 16) {
      throw new Error('INTERNAL_API_TOKEN must be set to at least 16 characters');
    }
    if (this.authMode === 'planning' && !this.planningBaseUrl) {
      throw new Error('PLANNING_BASE_URL is required when AUTH_MODE=planning');
    }
    if (!Number.isInteger(this.port) || this.port <= 0) {
      throw new Error('PORT must be a positive integer');
    }
  }
}
