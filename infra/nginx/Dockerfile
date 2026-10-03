# Edge Nginx (requirements §18): TLS termination, the React SPA (multi-stage build) and the
# /api, /ws and /live proxies. Build context: repository root.
FROM node:22-alpine AS portal
WORKDIR /srv/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# The generated API client is committed (make gen-api); the build type-checks against it.
RUN npm run build

FROM nginx:stable-alpine
# upgrade: pick up security fixes released after the base image was built (CI Trivy gate).
RUN apk upgrade --no-cache && rm /etc/nginx/conf.d/default.conf
COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf
COPY infra/nginx/templates/ /etc/nginx/templates/
COPY --from=portal /srv/frontend/dist /usr/share/nginx/html
EXPOSE 80 443
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://127.0.0.1/healthz || exit 1
