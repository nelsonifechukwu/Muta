#!/usr/bin/env bash
set -euo pipefail

campaign_root="${1:-/home/elijahnelson/Muta/bench/measurements/campaign-20260913-balanced-models}"
model_root="$campaign_root/models"
mkdir -p "$model_root"

fetch_model() {
    local filename="$1"
    local url="$2"
    local expected_bytes="$3"
    local expected_sha256="$4"
    local destination="$model_root/$filename"
    local partial="$destination.part"

    if [[ ! -f "$destination" ]]; then
        echo "downloading $filename"
        curl --fail --location --retry 5 --retry-all-errors \
            --continue-at - --output "$partial" "$url"
        mv "$partial" "$destination"
    fi

    local actual_bytes
    local actual_sha256
    actual_bytes="$(wc -c < "$destination" | tr -d ' ')"
    actual_sha256="$(sha256sum "$destination" | awk '{print $1}')"

    if [[ "$actual_bytes" != "$expected_bytes" ]]; then
        echo "size mismatch for $filename: expected $expected_bytes, got $actual_bytes" >&2
        exit 1
    fi
    if [[ "$actual_sha256" != "$expected_sha256" ]]; then
        echo "SHA-256 mismatch for $filename: expected $expected_sha256, got $actual_sha256" >&2
        exit 1
    fi
    printf '%s\t%s\t%s\n' "$filename" "$actual_bytes" "$actual_sha256"
}

fetch_model \
    "LFM2.5-1.2B-Thinking-Q4_0.gguf" \
    "https://huggingface.co/LiquidAI/LFM2.5-1.2B-Thinking-GGUF/resolve/9584426effbfa44b677e925793a12188a36b44ce/LFM2.5-1.2B-Thinking-Q4_0.gguf" \
    "695751680" \
    "cbabfbf76fdb35f0fc9bc8bf175cbb25173060bc8ff14b9b7d81d3c7a84fc16f"

fetch_model \
    "MiniCPM5-1B-F16.gguf" \
    "https://huggingface.co/openbmb/MiniCPM5-1B-GGUF/resolve/3d55fac80935ae6456986ad2384b5cbcc4d6c948/MiniCPM5-1B-F16.gguf" \
    "2166551936" \
    "68c40b08b1242754a107b9510af89aa75b10c75843ca7844643c70956b7f1e3d"

fetch_model \
    "Qwen3.5-2B-Q4_0.gguf" \
    "https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/f6d5376be1edb4d416d56da11e5397a961aca8ae/Qwen3.5-2B-Q4_0.gguf" \
    "1214873856" \
    "cd70221bebaee0503e0f6717e174250cd7825aa88438b3aabec9ad55731d9bb1"

fetch_model \
    "Qwen3-1.7B-Q4_0.gguf" \
    "https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/d7f544eead698dbd1f15126ef60b45a1e1933222/Qwen3-1.7B-Q4_0.gguf" \
    "1056782912" \
    "c876f159707a4e4f70e045106c69db15bfc935a4981706fd4f65c6e7ea1e81c5"

fetch_model \
    "LFM2.5-2.6B-Q4_0.gguf" \
    "https://huggingface.co/LiquidAI/LFM2.5-2.6B-GGUF/resolve/84022ce711b28455e8c4fc364ce68c00cf995875/LFM2.5-2.6B-Q4_0.gguf" \
    "1593894912" \
    "e1a61bf937bc60726e18626e97f7ee9bfd2574d95744c2ed909de98b78006fbe"

fetch_model \
    "Spark-X2.5-1.7B-Q4_K_M.gguf" \
    "https://huggingface.co/XHToken/Spark-X2.5-1.7B-GGUF/resolve/23e1fcac55e7dd71e4c12a23723cc228ba0e5e85/Spark-X2.5-1.7B-Q4_K_M.gguf" \
    "1107457856" \
    "902bde2522394954ac17821b3e5fd0df02defbc6944f122253f2580acf0503f4"

fetch_model \
    "MiniCPM5-2B-Q4_K_M.gguf" \
    "https://huggingface.co/openbmb/MiniCPM5-2B-GGUF/resolve/2079a22f3beaa4e306449978533478fe0522f4b3/MiniCPM5-2B-Q4_K_M.gguf" \
    "1561318368" \
    "ec2d5801640099e97d8d7e8003ad4d81f336e757811f03a26173dddf386602fd"

fetch_model \
    "LFM2.5-2.6B-QAD-Q4_0.gguf" \
    "https://huggingface.co/LiquidAI/LFM2.5-2.6B-GGUF/resolve/84022ce711b28455e8c4fc364ce68c00cf995875/LFM2.5-2.6B-QAD-Q4_0.gguf" \
    "1593894944" \
    "a247afd6414918eac8e520a9e6137dc271235461ecbe1180462221d5b8d40b03"

fetch_model \
    "MiniCPM5-1B-Q4_K_M.gguf" \
    "https://huggingface.co/openbmb/MiniCPM5-1B-GGUF/resolve/3d55fac80935ae6456986ad2384b5cbcc4d6c948/MiniCPM5-1B-Q4_K_M.gguf" \
    "688065920" \
    "81b64d05a23b17b34c475f42b3e72fbde62d4b92cc34541f7a8031d0752deafa"

fetch_model \
    "Qwen3.5-2B-Q4_K_M.gguf" \
    "https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/f6d5376be1edb4d416d56da11e5397a961aca8ae/Qwen3.5-2B-Q4_K_M.gguf" \
    "1280835840" \
    "aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223"

fetch_model \
    "VibeThinker-1.5B-q4_k_m.gguf" \
    "https://huggingface.co/sirunchained/VibeThinker-1.5B-gguf/resolve/d6a1e0f48176eeaf69b616f7c1a22dc915cbf11c/VibeThinker-1.5B-q4_k_m.gguf" \
    "1117320960" \
    "3df5dae7a65dfd426c8dc58d97ed1247af4b669bc2674c5f9b2b34103b01e164"

fetch_model \
    "Falcon-H1R-0.6B-Q4_K_M.gguf" \
    "https://huggingface.co/tiiuae/Falcon-H1-Tiny-R-0.6B-GGUF/resolve/b01e1ba5d4604914e5dcbd84cf387f4762212a8c/Falcon-H1R-0.6B-Q4_K_M.gguf" \
    "374177184" \
    "f41497801e96268876a681e65edc7155d15e255bd3de907b6bb29590744b6b74"

fetch_model \
    "nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf" \
    "https://huggingface.co/bartowski/nvidia_OpenReasoning-Nemotron-1.5B-GGUF/resolve/9b6c802caafdc99c2924ddb374c5a5995f0bb2f1/nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf" \
    "986046784" \
    "7c39e6fa1f335bec37e51404d104b47de0b80aafeaae534080aa8c2e11c71101"
