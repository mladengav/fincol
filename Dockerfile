# syntax=docker/dockerfile:1.7

# Pinned in one place so builder and runtime stay in lockstep.
ARG PYTHON_IMAGE=python:3.14-slim-trixie

# ---------------------------------------------------------------------------
# Stage 1: builder
# Resolve and install dependencies into a self-contained venv at /app/.venv
# using uv (copied from the official Astral image).
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Install runtime dependencies first, without the project itself, so this
# layer is reused whenever only source files change.
COPY pyproject.toml README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project

# Add the project sources and install the package itself into the venv,
# which materializes the `fincol`, `fincol_test_cli`, and `yf-cli` console scripts.
COPY . ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

# ---------------------------------------------------------------------------
# Stage 2: runtime
# Minimal image: stock Python plus the prebuilt venv and project source.
# uv is intentionally NOT carried over, so the runtime image stays slim.
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv

RUN groupadd --system app \
 && useradd --system --gid app --home-dir /app --no-create-home app \
 && mkdir -p /app/cache \
 && chown -R app:app /app

WORKDIR /app

COPY --from=builder --chown=app:app /app /app

# Re-assert ownership of /app and /app/cache: the COPY above only chowns the
# files it places, not the pre-existing target directory. fincol writes into
# /app/cache (CsvFincolIo._DEFAULT_FOLDER), so the app user must own it.
RUN chown app:app /app /app/cache

USER app

# Declare the cache as a volume so it can be bind-mounted or backed by a
# named volume for persistence across container runs.
VOLUME ["/app/cache"]

ENTRYPOINT ["fincol"]
CMD ["--help"]
