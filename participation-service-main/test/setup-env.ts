// Runs before the e2e tests load the app. Requires a migrated Postgres (see README).
process.env.NODE_ENV = 'test';
process.env.AUTH_MODE = 'dev';
process.env.INTERNAL_API_TOKEN = 'test-internal-token-0123456789';
process.env.DATABASE_URL =
  process.env.DATABASE_URL ?? 'postgresql://participation:participation@localhost:5433/participation';
