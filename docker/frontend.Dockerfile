# Frontend image — nginx serving the landing page + app and proxying /v1 to the backend.
# Third-party assets are either fetched at BUILD time with pinned versions (the established
# Markdown/KaTeX stack) or copied from checked-in, hash-verified bundles (visual renderers), so
# the served page is fully offline at runtime: no CDN, ever.
FROM --platform=linux/amd64 nginx:1.27-alpine

WORKDIR /usr/share/nginx/html/chat
# curl (not busybox wget): GitHub's signed release redirects need real TLS + redirect
# handling; busybox wget fails on them under emulation.
RUN apk add --no-cache curl \
 && mkdir -p vendor/viz \
 && curl -fsSL --retry 3 https://github.com/KaTeX/KaTeX/releases/download/v0.16.11/katex.tar.gz \
      | tar xz -C vendor \
 && curl -fsSL --retry 3 -o vendor/marked.min.js https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js \
 && curl -fsSL --retry 3 -o vendor/purify.min.js https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js \
 && test -f vendor/katex/katex.min.js && test -f vendor/katex/katex.min.css \
 && apk del curl

# Rendered to /etc/nginx/conf.d/default.conf at start by the image's envsubst entrypoint,
# substituting ${BACKEND_UPSTREAM} (see docker-compose.yml / run.sh --native).
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY ui/ /usr/share/nginx/html/chat/
RUN printf '%s  %s\n' \
      f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539 vendor/viz/d3.v7.9.0.min.js \
      170c6789f43217c96b3170f4b42fafe135de7f7cd48497a4218f9757ee1d49fa vendor/viz/three.r160.min.js \
      96c01b81f44a3290e2b4532f55e2c9534b2adc43273a19f3756b2cb41f0fd0b6 vendor/viz/gsap.v3.13.0.min.js \
      b5ce1be3c3f530f192e0f2571d1942846096d66119cbada34bfdc912c4873f35 vendor/viz/anime.v3.2.2.min.js \
      1137223e57ddbf0e60be9e08340e529e6e2ae4967650b39212fe97f4e57285ea vendor/viz/motion.v11.11.13.js \
      | sha256sum -c -
COPY landing/ /usr/share/nginx/html/
