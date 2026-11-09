# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Backend image — ResumeTailor-AI (FastAPI + RenderCV + Playwright)
#
# Design goals
#   * Reproducible: `docker compose up --build` is the only command needed.
#   * Fast to rebuild: the dependency layer only changes when
#     requirements.txt / requirements-dev.txt change.
#   * Lean runtime: no compilers, no pip cache, no apt lists, no build
#     tooling in the final layer.
#   * Chromium is downloaded ONCE at build time instead of on every
#     container start (the previous ad-hoc container ran
#     `playwright install chromium` on each boot).
# ---------------------------------------------------------------------------

# ---------- Stage 1: python dependencies + Chromium binaries ---------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

WORKDIR /build

# Only the dependency manifests live in this layer, so touching application
# code does not invalidate the (expensive) wheel + Chromium download.
COPY requirements.txt requirements-dev.txt ./

# `playwright install chromium --only-shell` fetches ONLY the headless shell
# (Chrome Headless Shell), which is the binary Playwright actually launches
# for every `chromium.launch(headless=True)` call in `backend/`. The default
# `playwright install chromium` ALSO downloads the full Chromium build
# (~403 MB) that nothing here uses — every call is headless, and none of
# them passes `channel=`, so the full build would be dead weight.
# Downloading only the shell saves ~430 MB of image.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
 && /opt/venv/bin/pip install -r requirements.txt -r requirements-dev.txt \
 && /opt/venv/bin/python -m playwright install chromium --only-shell


# ---------- Stage 2: runtime ----------------------------------------------
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="ResumeTailor-AI backend" \
      org.opencontainers.image.description="ATS resume tailor — FastAPI + RenderCV + Playwright" \
      org.opencontainers.image.source="https://github.com/JOspitia/jd-to-resume-v2"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    TZ=UTC

WORKDIR /app

# Copy the virtualenv and the Playwright browser bundle from the builder.
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/ms-playwright /opt/ms-playwright

# System packages:
#   fonts-freefont-ttf / fonts-dejavu-core -> the fonts Chromium and Typst
#       use when typesetting the PDF.
#   `playwright install-deps` -> the shared libraries Chromium needs
#       (libnss3, libatk, libgbm, ...). It only installs system packages;
#       the browser binary itself already comes from the builder stage.
#
# `playwright install-deps` is deliberately used instead of a hand-written
# package list: it knows the right package names for the base image's
# Debian release (the t64 renames change between releases). The purge that
# follows trims what Chromium headless never loads:
#   * fonts-unifont / fonts-wqy-zenhei / fonts-ipafont-gothic /
#     fonts-noto-color-emoji -> ~70 MB of CJK/emoji fonts we don't use.
#   * xvfb -> only needed for headed mode; we always run headless.
# The purge happens inside the SAME layer, so those bytes never reach the
# image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        fonts-freefont-ttf \
        fonts-dejavu-core \
        curl \
 && /opt/venv/bin/python -m playwright install-deps chromium \
 && apt-get purge -y --auto-remove \
        fonts-unifont \
        fonts-wqy-zenhei \
        fonts-ipafont-gothic \
        fonts-noto-color-emoji \
        xvfb \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Application code (see .dockerignore: no .env, no caches, no output/).
COPY . /app

# Run as a non-root user. The named volume `jd-output` inherits the
# ownership of /app/output, so the container can write the PDFs it renders.
RUN useradd --create-home --uid 10001 appuser \
 && mkdir -p /app/output \
 && chown -R appuser:appuser /app/output \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# The healthcheck uses the app's own root endpoint; `curl` is already
# installed above, so no extra dependency is needed.
HEALTHCHECK --interval=15s --timeout=5s --start-period=25s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/ || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
