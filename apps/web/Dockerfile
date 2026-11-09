# Build from the repo root (pnpm workspace lockfile lives there):
#   docker build -f apps/web/Dockerfile -t stellar-lense-web .
# apps/web/Dockerfile.dockerignore keeps the context to the files used here.

FROM node:22-slim AS build
RUN corepack enable && corepack prepare pnpm@9.0.0 --activate
WORKDIR /repo
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile --filter @stellar-lense/web...
COPY apps/web apps/web
RUN pnpm --filter @stellar-lense/web build

FROM node:22-slim
RUN corepack enable && corepack prepare pnpm@9.0.0 --activate
WORKDIR /repo
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /repo /repo
WORKDIR /repo/apps/web
EXPOSE 3000
# API_URL is read at request time by the server components (src/lib/api.ts).
CMD ["pnpm", "start", "-p", "3000"]
