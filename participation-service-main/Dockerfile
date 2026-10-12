# syntax=docker/dockerfile:1
FROM scratch AS engine-artifacts
COPY .engine-artifacts/ /engines/

FROM node:22-bookworm-slim AS build
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends openssl && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json ./
RUN npm ci
COPY prisma ./prisma
COPY scripts/install-engine-cache.cjs ./scripts/install-engine-cache.cjs
# Optional verified artifacts support offline builds; binaries are ignored by Git.
RUN --mount=type=bind,from=engine-artifacts,source=/engines,target=/engine-artifacts \
    set -e; target=$(node -e "require('@prisma/get-platform').getBinaryTargetForCurrentPlatform().then(t=>process.stdout.write(t))"); \
    node scripts/install-engine-cache.cjs && \
    if [ -s /engine-artifacts/manifest.json ]; then \
      export PRISMA_SCHEMA_ENGINE_BINARY="/app/node_modules/@prisma/engines/schema-engine-$target"; \
      export PRISMA_QUERY_ENGINE_LIBRARY="/app/node_modules/@prisma/engines/libquery_engine-$target.so.node"; \
    fi; \
    npx prisma generate && cp "node_modules/@prisma/engines/schema-engine-$target" prisma/schema-engine
COPY tsconfig.json tsconfig.build.json nest-cli.json ./
COPY src ./src
RUN npm run build
# node_modules is deliberately not pruned: the prisma CLI (a devDependency) must stay available
# so the container can run `prisma migrate deploy` on start. Slimming this is a later optimisation.

FROM node:22-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production
ENV PRISMA_SCHEMA_ENGINE_BINARY=/app/prisma/schema-engine
RUN apt-get update && apt-get install -y --no-install-recommends openssl && rm -rf /var/lib/apt/lists/*
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/dist ./dist
COPY --from=build --chown=node:node /app/prisma ./prisma
COPY --chown=node:node package.json ./
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/health/ready').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
# Migrations run on start. `migrate deploy` takes a Postgres advisory lock, so several replicas
# starting together apply each migration once.
CMD ["sh", "-c", "npx prisma migrate deploy && node dist/main.js"]
