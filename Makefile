.PHONY: help up down logs migrate worker-cpu worker-cpu-watch api gpu-up backup-outputs test lint format

help:
	@echo "Cibles disponibles :"
	@echo "  up                Démarre l'infra docker-compose (Temporal + Postgres + MinIO + NATS)"
	@echo "  down              Arrête l'infra"
	@echo "  logs              Logs combinés"
	@echo "  migrate           Applique les migrations Alembic"
	@echo "  worker-cpu        Démarre cpu_worker en process direct"
	@echo "  worker-cpu-watch  Démarre cpu_worker avec hot reload"
	@echo "  api               Démarre l'API FastAPI (V1+)"
	@echo "  gpu-up            Active le worker GPU local (à lancer sur le PC, pas le Mac)"
	@echo "  backup-outputs    Copie les outputs MinIO vers ~/Documents/Road2Track/backups/"
	@echo "  test              Lance pytest"
	@echo "  lint              Lance ruff + pyright"
	@echo "  format            Reformate avec ruff format"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	uv run alembic -c packages/storage/migrations/alembic.ini upgrade head

worker-cpu:
	uv run python -m services.cpu_worker

worker-cpu-watch:
	uv run watchfiles "python -m services.cpu_worker" packages services/cpu_worker

api:
	uv run uvicorn services.api.src.main:app --reload --host 127.0.0.1 --port 8000

gpu-up:
	docker compose -f docker-compose.gpu.yml up -d

backup-outputs:
	mkdir -p ~/Documents/Road2Track/backups/$$(date +%Y-%m-%d)
	mc mirror minio/outputs/ ~/Documents/Road2Track/backups/$$(date +%Y-%m-%d)/

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run pyright

format:
	uv run ruff format .
	uv run ruff check --fix .
