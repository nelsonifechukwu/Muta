#!/usr/bin/env bash
# Deploy the Muta IQ report to Vercel as a prebuilt static site (docs/report-hosting.md).
#
# Flow: `vercel pull` refreshes the linked project's settings in .vercel/; `vercel build` runs
# vercel.json's buildCommand locally (muta-iq/dashboard/build_static.py -> site/) and packages
# site/ as Build Output; `vercel deploy --prebuilt` uploads only that output (~330 KiB). No
# repository sources are sent to Vercel and nothing is built there.
#
# Locally it needs the `vercel` CLI, a login, and a one-time `vercel link --yes --project muta-iq`.
# In CI (.github/workflows/vercel.yml) the link is replaced by VERCEL_ORG_ID + VERCEL_PROJECT_ID
# and the login by VERCEL_TOKEN, all read from the environment.
# Usage: scripts/deploy_report_vercel.sh [--preview]        (production by default)
set -euo pipefail
cd "$(dirname "$0")/.."

target=production
prod_flag=--prod
if [[ "${1:-}" == "--preview" ]]; then
  target=preview
  prod_flag=""
fi

# `${token_args[@]+"${token_args[@]}"}` expands to nothing when the array is empty; a plain
# "${token_args[@]}" is an unbound-variable error under `set -u` on macOS's bash 3.2.
token_args=()
if [[ -n "${VERCEL_TOKEN:-}" ]]; then
  token_args=(--token "$VERCEL_TOKEN")
fi

if [[ ! -f .vercel/project.json && ( -z "${VERCEL_ORG_ID:-}" || -z "${VERCEL_PROJECT_ID:-}" ) ]]; then
  echo "deploy_report_vercel: repository is not linked; run 'vercel link --yes --project muta-iq'" \
       "or export VERCEL_ORG_ID and VERCEL_PROJECT_ID" >&2
  exit 1
fi

vercel pull --yes --environment="$target" ${token_args[@]+"${token_args[@]}"}
# shellcheck disable=SC2086  # an empty prod_flag must expand to nothing
vercel build --yes $prod_flag ${token_args[@]+"${token_args[@]}"}
vercel deploy --prebuilt --yes $prod_flag ${token_args[@]+"${token_args[@]}"}
