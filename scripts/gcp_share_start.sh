#!/usr/bin/env bash
# Fetch the write-only fleet credential on the operator laptop, then start Muta's private GCP
# classroom relay. This explicit simulation launcher is never called by packaged offline builds.

# Do not let an inherited or explicit xtrace setting print the credential assignment below.
set +x
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
GCLOUD_BIN="${MUTA_GCLOUD_BIN:-gcloud}"
RELAY_SCRIPT="${MUTA_GCP_RELAY_SCRIPT:-$SCRIPT_DIR/gcp_share_relay.sh}"
PROJECT="${MUTA_GCP_PROJECT:-muta-adtc}"
FLEET_SECRET="${MUTA_GCP_FLEET_SECRET:-muta-fleet-ingest-key}"
FLEET_URL="${MUTA_FLEET_URL:-https://muta-fleet-ingest-3lobbxiywa-uc.a.run.app}"

# Fail before asking Secret Manager for anything when this was entered at the muta-vm prompt.
product_name_file="${MUTA_GCP_RELAY_PRODUCT_NAME_FILE:-/sys/class/dmi/id/product_name}"
if [ -r "$product_name_file" ] && grep -qi 'Google Compute Engine' "$product_name_file"; then
    printf '%s\n' \
        'gcp_share_start.sh must run on the operator laptop, not inside muta-vm.' \
        'Exit this SSH session, open a terminal on the laptop, and run it from the Muta folder.' >&2
    exit 1
fi

command -v "$GCLOUD_BIN" >/dev/null 2>&1 || {
    printf 'gcloud is required; install and authenticate the Google Cloud CLI first\n' >&2
    exit 1
}
[ -x "$RELAY_SCRIPT" ] || {
    printf 'GCP share relay is missing or not executable: %s\n' "$RELAY_SCRIPT" >&2
    exit 1
}

MUTA_FLEET_INGEST_KEY=$(
    "$GCLOUD_BIN" secrets versions access latest \
        "--project=$PROJECT" \
        "--secret=$FLEET_SECRET"
)
[ -n "$MUTA_FLEET_INGEST_KEY" ] || {
    printf 'Secret Manager returned an empty fleet ingest key\n' >&2
    exit 1
}

export MUTA_FLEET_URL="$FLEET_URL"
export MUTA_FLEET_INGEST_KEY
export MUTA_GCP_PROJECT="$PROJECT"
cleanup_secret() {
    unset MUTA_FLEET_INGEST_KEY MUTA_FLEET_URL MUTA_GCP_PROJECT
}
trap cleanup_secret EXIT

"$RELAY_SCRIPT" "$@"
