# Frontend image — nginx serving the static UI and proxying /v1 to the backend.
# Vendored assets are fetched at BUILD time (pinned versions) so the served page is fully
# offline at runtime: no CDN, ever.
FROM --platform=linux/amd64 nginx:1.27-alpine

WORKDIR /usr/share/nginx/html
RUN mkdir -p vendor \
 && wget -qO- https://github.com/KaTeX/KaTeX/releases/download/v0.16.11/katex.tar.gz \
      | tar xz -C vendor \
 && wget -qO vendor/marked.min.js https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js \
 && wget -qO vendor/purify.min.js https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY ui/ /usr/share/nginx/html/
