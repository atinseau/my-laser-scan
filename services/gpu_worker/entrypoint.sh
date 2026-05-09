#!/usr/bin/env bash
set -euo pipefail

# Démarrer Tailscale en arrière-plan si TS_AUTHKEY est défini.
if [[ -n "${TS_AUTHKEY:-}" ]]; then
    echo "[entrypoint] Joining Tailscale mesh..."
    tailscaled --tun=userspace-networking --state=mem: &
    sleep 2
    tailscale up --authkey="${TS_AUTHKEY}" --hostname="gpu-worker-$(hostname)" --accept-routes
    echo "[entrypoint] Tailscale OK"
fi

# Lancer la commande passée à docker run
exec "$@"
