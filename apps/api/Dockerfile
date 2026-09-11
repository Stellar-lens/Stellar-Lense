# apps/api is a member of the shared uv workspace rooted at the monorepo
# root (one pyproject.toml + one uv.lock covering apps/api and
# packages/core together — see /pyproject.toml's [tool.uv.workspace] and
# apps/api/pyproject.toml). That means this build needs the repo root as
# its context, not apps/api itself.
#
# Point your platform's "Dockerfile path" at apps/api/Dockerfile and its
# build context / root directory at the repo root. Building by hand:
#
#   docker build -f apps/api/Dockerfile -t stellar-lense-api .
#
# (run from the repo root — the trailing "." is the build context).

FROM python:3.12-slim

# Static uv binary from Astral's official distroless image — faster and
# more reproducible than pip-installing uv into the build.
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /usr/local/bin/

WORKDIR /workspace

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Workspace-level files first, so the dependency-install layer only
# invalidates when a pyproject.toml/uv.lock actually changes, not on every
# apps/api source edit.
COPY pyproject.toml uv.lock ./
# packages/core is a workspace member the lockfile resolves against; uv
# needs its pyproject.toml present to validate the workspace even though
# stellar-lense-api doesn't depend on it at runtime. Its actual source is
# excluded via .dockerignore.
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY apps/api apps/api

# --package scopes the sync to apps/api's own dependency set (fastapi,
# scikit-learn, etc.) rather than the whole workspace's (which would also
# pull in packages/core's — much heavier — dependency set).
RUN uv sync --frozen --no-dev --package stellar-lense-api --project apps/api

ENV PATH="/workspace/.venv/bin:${PATH}"
WORKDIR /workspace/apps/api

EXPOSE 8000

# Railway/Fly/Render inject PORT; default to 8000 for a plain `docker run`.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
