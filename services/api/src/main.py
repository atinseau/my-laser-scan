"""API HTTP FastAPI — exposée sur Tailscale (V1+, cf. specs/01-cahier-des-charges.md §3.2).

À implémenter à partir de l'It. 2 (app iOS native).
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="Road2Track API",
    description="API de gestion des projets, sessions de capture et workflows de traitement.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
