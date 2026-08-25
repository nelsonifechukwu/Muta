#!/usr/bin/env bash
# Deploy the Muta IQ report to Vercel as a prebuilt static site (docs/report-hosting.md).
#
# Flow: `vercel pull` refreshes the linked project's settings in .vercel/; `vercel build` runs
# vercel.json's buildCommand locally (muta-iq/dashboard/build_static.py -> site/) and packages
# site/ as Build Output; `vercel deploy --prebuilt` uploads only that output (~330 KiB). No
# repository sources are sent to Vercel and nothing is built there.
#
# Requires the `vercel` CLI, a login, and a one-time link: `vercel link --yes --project muta-iq`.
# Usage: scripts/deploy_report_vercel.sh [--preview]        (production by default)
set -euo pipefail
cd "$(dirname "$0")/.."

target=production
prod_flag=--prod
if [[ "${1:-}" == "--preview" ]]; then
  target=preview
  prod_flag=""
fi

if [[ ! -f .vercel/project.json ]]; then
  echo "deploy_report_vercel: repository is not linked; run 'vercel link --yes --project muta-iq' first" >&2
  exit 1
fi

vercel pull --yes --environment="$target"
# shellcheck disable=SC2086  # an empty prod_flag must expand to nothing
vercel build --yes $prod_flag
vercel deploy --prebuilt --yes $prod_flag
