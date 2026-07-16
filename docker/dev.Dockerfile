# Development image — linux/amd64 from day one so binaries are already x86-64 ELF and the
# 9 Aug step is extraction, not a rebuild (ROADMAP A.1/A.4, 14 Jul).
#   docker buildx build --platform=linux/amd64 -f docker/dev.Dockerfile -t muta-dev .
FROM --platform=linux/amd64 ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git \
        python3.10 python3-pip \
        lm-sensors ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN python3.10 -m pip install --no-cache-dir --upgrade pip \
    && python3.10 -m pip install --no-cache-dir -e ".[dev]"

# TODO(Lane A, 15 Jul): clone + build llama.cpp here
#   (-DGGML_NATIVE=OFF -DGGML_AVX2=ON -DGGML_AVX512=OFF -DGGML_F16C=ON -DGGML_FMA=ON).

EXPOSE 8000
CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
