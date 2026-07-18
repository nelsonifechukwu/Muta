# Development image — linux/amd64 from day one so binaries are already x86-64 ELF and the
# 9 Aug step is extraction, not a rebuild (ROADMAP A.1/A.4, 14 Jul).
#   docker buildx build --platform=linux/amd64 -f docker/dev.Dockerfile -t muta-dev .
#
# Two stages: build llama.cpp once in a toolchain-heavy stage, then ship only the binaries
# next to the app. The compiler never reaches the final image, which keeps it closer to what
# gets extracted onto the flash drive.

# ---------------------------------------------------------------------------
# Stage 1 — build the inference engine
# ---------------------------------------------------------------------------
FROM --platform=linux/amd64 ubuntu:22.04 AS engine

ENV DEBIAN_FRONTEND=noninteractive
# `file` and `binutils` are for the ISA assertion below, not the compile — build-essential
# ships binutils but not file, and discovering that after the compile wastes the build.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git ca-certificates \
        file binutils \
    && rm -rf /var/lib/apt/lists/*

# Pinned in runtime/VERSIONS.md — the 9 Aug extraction must reproduce this exact binary.
ARG LLAMA_CPP_REF=b10035

WORKDIR /src
RUN git clone --depth 1 --branch ${LLAMA_CPP_REF} https://github.com/ggml-org/llama.cpp.git .

# AVX2 is the baseline and AVX-512 is forbidden: much of the target field (Zen 3, 12th-gen
# consumer Intel) faults on AVX-512, and an illegal-instruction fault is a hard failure —
# disqualification, not a deduction. GGML_NATIVE=OFF stops cmake from tuning to whatever
# CPU happens to build the image; runtime feature detection handles wider ISA.
# LLAMA_CURL=OFF drops the -hf model puller (and libcurl): deploy is offline, and
# runtime/models.py provisions weights itself.
RUN cmake -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_NATIVE=OFF \
        -DGGML_AVX2=ON \
        -DGGML_AVX512=OFF \
        -DGGML_F16C=ON \
        -DGGML_FMA=ON \
        -DLLAMA_CURL=OFF \
        -DLLAMA_BUILD_TESTS=OFF \
        -DLLAMA_BUILD_EXAMPLES=OFF \
        -DLLAMA_BUILD_SERVER=ON \
        -DBUILD_SHARED_LIBS=OFF \
    && cmake --build build --config Release -j "$(nproc)" \
        --target llama-server llama-bench

# Fail the build here rather than on the target box if the wrong ISA slipped in.
RUN set -eux; \
    file build/bin/llama-server | grep -q 'ELF 64-bit LSB.*x86-64'; \
    if objdump -d build/bin/llama-server | grep -qE '\s(vpxord|vpternlogd|kmovw|vpbroadcastmw2d)\s'; then \
        echo 'FATAL: AVX-512 instructions found in llama-server'; exit 1; \
    fi

# ---------------------------------------------------------------------------
# Stage 2 — the app
# ---------------------------------------------------------------------------
FROM --platform=linux/amd64 ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3-pip \
        lm-sensors ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN python3.10 -m pip install --no-cache-dir --upgrade pip \
    && python3.10 -m pip install --no-cache-dir -e ".[dev]"

# Where runtime/server.py:find_binary() looks first after the env override.
COPY --from=engine /src/build/bin/llama-server /app/runtime/build/bin/
COPY --from=engine /src/build/bin/llama-bench  /app/runtime/build/bin/

# Build-time provenance. .dockerignore excludes .git and this image has no git binary, so a
# benchmark run inside the container cannot discover its own commit — and the 9-11 Aug report
# numbers come from exactly here. A number without provenance is unusable in the report
# (ROADMAP 16 Jul), so inject it rather than shipping .git.
#   docker buildx build --build-arg MUTA_GIT_SHA=$(git rev-parse HEAD) ...
ARG MUTA_GIT_SHA=unknown
ENV MUTA_GIT_SHA=${MUTA_GIT_SHA}

# Weights are provisioned, never baked: a 378 MB layer would bloat every push, and
# .dockerignore already excludes models/*.gguf. Mount -v ./models:/app/models.
ENV MUTA_RT_MODEL_DIR=/app/models \
    MUTA_RT_DB_PATH=/app/data/muta.sqlite3 \
    MUTA_RT_LLAMA_SERVER_BIN=/app/runtime/build/bin/llama-server

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
