# Frontend image — nginx serving the static UI and proxying /v1 to the backend.
# Vendored assets are fetched at BUILD time (pinned versions) so the served page is fully
# offline at runtime: no CDN, ever.
FROM --platform=linux/amd64 nginx:1.27-alpine

WORKDIR /usr/share/nginx/html
# curl (not busybox wget): GitHub's signed release redirects need real TLS + redirect
# handling; busybox wget fails on them under emulation.
RUN apk add --no-cache curl \
 && mkdir -p vendor \
 && curl -fsSL --retry 3 https://github.com/KaTeX/KaTeX/releases/download/v0.16.11/katex.tar.gz \
      | tar xz -C vendor \
 && curl -fsSL --retry 3 -o vendor/marked.min.js https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js \
 && curl -fsSL --retry 3 -o vendor/purify.min.js https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js \
 && test -f vendor/katex/katex.min.js && test -f vendor/katex/katex.min.css \
 && apk del curl

# Rendered to /etc/nginx/conf.d/default.conf at start by the image's envsubst entrypoint,
# substituting ${BACKEND_UPSTREAM} (see docker-compose.yml / run.sh --native).
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY ui/ /usr/share/nginx/html/
