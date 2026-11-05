#!/usr/bin/env bash
# Deploy Deskhand to Azure App Service (Linux container), reachable from ONE IP only.
#
# UNTESTED: written 2026-11-05 and never run. Review every command before --apply.
# Without --apply it only prints the commands.
#
#   RG=hedgerow-secscan ACR=<registry> APP=<app-name> ALLOWED_IP=<your-ip> \
#     deskhand/deploy/azure.sh [--apply]
#
# Run from the repo root. No secret is passed here: the default backend is the stub.
# For a hosted model, put its key in Key Vault and reference it as the app setting
# DESKHAND_LLM_API_KEY (a Key Vault reference), never on a command line.
set -euo pipefail

: "${RG:?set RG}" "${ACR:?set ACR}" "${APP:?set APP}" "${ALLOWED_IP:?set ALLOWED_IP (the one address allowed in)}"
PLAN="${PLAN:-${APP}-plan}"
TAG="${TAG:-$(git rev-parse --short HEAD)}"
IMAGE="${ACR}.azurecr.io/deskhand:${TAG}"

run() {
  if [[ "${1:-}" == "--apply" ]]; then shift; "$@"; else printf '+'; printf ' %q' "$@"; echo; fi
}
MODE="${1:-}"

run $MODE az acr build --registry "$ACR" --image "deskhand:${TAG}" --file deskhand/Dockerfile deskhand
run $MODE az appservice plan create -g "$RG" -n "$PLAN" --is-linux --sku B1
# Create the app on a harmless placeholder image, lock it down, and only then switch
# it to Deskhand, so the vulnerable image is never reachable before the restrictions.
run $MODE az webapp create -g "$RG" -p "$PLAN" -n "$APP" \
  --container-image-name mcr.microsoft.com/appsvc/staticsite:latest \
  --assign-identity "[system]" --acr-use-identity
# Deny by default, then allow the one address. Never skip this: every gap is real.
run $MODE az webapp config access-restriction set -g "$RG" -n "$APP" --default-action Deny
run $MODE az webapp config access-restriction add -g "$RG" -n "$APP" --rule-name allowed \
  --action Allow --ip-address "${ALLOWED_IP}/32" --priority 100
run $MODE az webapp config appsettings set -g "$RG" -n "$APP" --settings WEBSITES_PORT=8300
# Known gap in this script: the app's identity is never given the AcrPull role on the
# registry, so the pull below will fail until that role is assigned.
run $MODE az webapp config container set -g "$RG" -n "$APP" --container-image-name "$IMAGE"
