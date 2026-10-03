# FaceTrack portal: static build served by Nginx (the main Nginx proxies /api and /ws; see infra/).
# Build context: repository root.
FROM node:22-alpine AS build
WORKDIR /srv/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# The generated API client is committed (make gen-api); the build type-checks against it.
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /srv/frontend/dist /usr/share/nginx/html
COPY frontend/nginx-spa.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
