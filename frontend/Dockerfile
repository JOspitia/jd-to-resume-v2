# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Frontend image — ResumeTailor-AI (React + Vite + nginx)
#
# Stage 1 compiles the Vite bundle; stage 2 serves it with nginx, which also
# reverse-proxies /api to the backend container. Because the proxy is
# same-origin, the production bundle can use relative URLs and no CORS or
# rebuild-per-environment is needed.
# ---------------------------------------------------------------------------

# ---------- Stage 1: build the bundle -------------------------------------
FROM node:24-alpine AS builder

# NOTE: do NOT set NODE_ENV=production here. npm skips `devDependencies`
# when NODE_ENV=production, and the toolchain that builds the bundle
# (typescript, vite, tailwind, postcss) lives in devDependencies.
ENV npm_config_update_notifier=false

WORKDIR /build

# Lockfile-only layer: `npm ci` is re-run only when the dependencies change.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Application source.
COPY . .

# `npm run build` == `tsc -b && vite build`, so a type error fails the image
# build instead of shipping a broken bundle.
RUN npm run build


# ---------- Stage 2: runtime (nginx) --------------------------------------
FROM nginx:1.27-alpine AS runtime

LABEL org.opencontainers.image.title="ResumeTailor-AI frontend" \
      org.opencontainers.image.description="Static React bundle served by nginx with an /api reverse proxy" \
      org.opencontainers.image.source="https://github.com/JOspitia/jd-to-resume-v2"

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# nginx:alpine runs as root by default and drops privileges to the
# `nginx` user for the workers; the listen port must stay > 1024.
EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
