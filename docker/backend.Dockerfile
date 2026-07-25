# Backend image — llama-server + the FastAPI gateway, linux/amd64.
#   docker compose build backend
#
# Two stages: build llama.cpp once in a toolchain-heavy stage, then ship only the binaries
# next to the app. The compiler never reaches the final image.

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

# Pinned in runtime/VERSIONS.md.
ARG LLAMA_CPP_REF=b10035

WORKDIR /src
RUN git clone --depth 1 --branch ${LLAMA_CPP_REF} https://github.com/ggml-org/llama.cpp.git .

# AVX2 is the baseline and AVX-512 is forbidden: much of the field (Zen 3, 12th-gen
# consumer Intel) faults on AVX-512, and an illegal-instruction fault is a hard failure.
# GGML_NATIVE=OFF stops cmake from tuning to whatever CPU happens to build the image;
# runtime feature detection handles wider ISA. LLAMA_CURL=OFF drops the -hf model puller
# (and libcurl): runtime/models.py provisions weights itself.
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

# Fail the build here rather than on a target box if the wrong ISA slipped in.
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
# curl: compose healthcheck. ffmpeg: /v1/audio/transcribe decodes browser uploads
# (webm/opus/m4a) to 16 kHz PCM. lm-sensors: thermal telemetry on Linux hosts.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3-pip \
        curl ffmpeg lm-sensors ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Dependency layer keyed on pyproject.toml alone, so a source edit doesn't re-resolve and
# re-download every wheel. sherpa-onnx is wheels-only on purpose: an sdist build would need
# a C++ toolchain this stage deliberately lacks — fail loudly instead of compiling for an hour.
COPY pyproject.toml /app/pyproject.toml
RUN python3.10 -m pip install --no-cache-dir --upgrade pip \
    && python3.10 -m pip install --no-cache-dir tomli \
    && python3.10 -c "import tomli; d = tomli.load(open('pyproject.toml','rb'))['project']; \
print('\n'.join(d['dependencies'] + d['optional-dependencies']['dev']))" > /tmp/reqs.txt \
    && python3.10 -m pip install --no-cache-dir -r /tmp/reqs.txt \
    && python3.10 -m pip install --no-cache-dir --only-binary=:all: "sherpa-onnx>=1.10"
COPY . .
RUN python3.10 -m pip install --no-cache-dir --no-deps -e ".[dev]"

# Where runtime/server.py:find_binary() looks first after the env override.
COPY --from=engine /src/build/bin/llama-server /app/runtime/build/bin/
COPY --from=engine /src/build/bin/llama-bench  /app/runtime/build/bin/

# Build-time provenance: .dockerignore excludes .git and the image has no git binary.
ARG MUTA_GIT_SHA=unknown
ENV MUTA_GIT_SHA=${MUTA_GIT_SHA}

# Weights are provisioned, never baked. Mount -v ./models:/app/models.
ENV MUTA_RT_MODEL_DIR=/app/models \
    MUTA_RT_LLAMA_SERVER_BIN=/app/runtime/build/bin/llama-server \
    TUTOR_ROOT=/app

EXPOSE 8000
CMD ["python3.10", "-m", "uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
