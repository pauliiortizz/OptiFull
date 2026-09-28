#!/usr/bin/env bash
# Dispara un deploy en Render (Deploy Hook) de un commit exacto y espera a que
# el servicio quede corriendo ESE commit (via /api/health).
#
# Uso:  deploy_render.sh <SERVICE_URL> <COMMIT_SHA>
# Env:  RENDER_DEPLOY_HOOK_URL  (secret del environment; NO se imprime)
#       TIMEOUT_MIN             (default 15: build de Docker + arranque en frio)
set -euo pipefail

URL="${1:?falta SERVICE_URL}"; URL="${URL%/}"
SHA="${2:?falta COMMIT_SHA}"
: "${RENDER_DEPLOY_HOOK_URL:?falta el secret RENDER_DEPLOY_HOOK_URL}"
TIMEOUT_MIN="${TIMEOUT_MIN:-15}"

echo "Disparando deploy de ${SHA} en ${URL} ..."
HTTP=$(curl -sS -o /tmp/hook_response.json -w '%{http_code}' -X POST "${RENDER_DEPLOY_HOOK_URL}&ref=${SHA}")
if [[ "$HTTP" != 2* ]]; then
  echo "::error::Render rechazo el Deploy Hook (HTTP ${HTTP})"
  cat /tmp/hook_response.json || true
  exit 1
fi
echo "Deploy encolado en Render (HTTP ${HTTP})."

DEADLINE=$(( $(date +%s) + TIMEOUT_MIN * 60 ))
while (( $(date +%s) < DEADLINE )); do
  BODY=$(curl -sS --max-time 30 "${URL}/api/health" 2>/dev/null || true)
  RUNNING=$(echo "$BODY" | jq -r '.commit // empty' 2>/dev/null || true)
  if [[ "$RUNNING" == "$SHA" ]]; then
    echo "OK: ${URL} corre el commit ${SHA}. Health: ${BODY}"
    exit 0
  fi
  echo "  esperando... (corriendo: ${RUNNING:-sin respuesta})"
  sleep 15
done

echo "::error::Timeout (${TIMEOUT_MIN} min): ${URL} no llego a correr el commit ${SHA}. Revisa los logs del deploy en Render."
exit 1
