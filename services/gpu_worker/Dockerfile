# Image GPU worker — CUDA pur.
# NE contient PAS Wine ni ksEditor (cf. specs/05-infrastructure.md §5.1, image distincte wine-worker prévue à l'It. 1).

FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# --- Outils système + Python 3.12 + ffmpeg (probe + drop audio dans ingest_session) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
        curl \
        ca-certificates \
        gnupg \
        git \
        iproute2 \
        iptables \
        ffmpeg \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-dev \
        python3.12-venv \
    && rm -rf /var/lib/apt/lists/*

# --- uv (gestionnaire de dépendances) ---
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

# --- Tailscale ---
RUN curl -fsSL https://tailscale.com/install.sh | sh

WORKDIR /app

# --- Workspace ---
COPY pyproject.toml uv.lock* ./
COPY packages packages
COPY services/gpu_worker services/gpu_worker

# Installer les dépendances avec extras GPU (gsplat, 2DGS, transformers, open3d, pytorch3d)
# TODO It. 0 : compléter quand les versions sont fixées
# RUN uv sync --frozen --extra gpu --package road2track-gpu-worker

# --- Pré-bake des modèles ML essentiels (ADR-020) ---
# TODO It. 0 : Mask2Former + gsplat checkpoints
# RUN uv run python -c "from transformers import Mask2FormerForUniversalSegmentation; \
#     Mask2FormerForUniversalSegmentation.from_pretrained('facebook/mask2former-swin-large-cityscapes-semantic')"

# --- Entrypoint qui démarre Tailscale puis le worker ---
COPY services/gpu_worker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uv", "run", "python", "-m", "services.gpu_worker"]
