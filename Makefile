.PHONY: help build up down run send-report scheduler logs test

help:
	@echo "make build        Build the local Docker image"
	@echo "make up           Start the local stack"
	@echo "make down         Stop the local stack"
	@echo "make run          Run one collection and analysis cycle"
	@echo "make send-report  Send the latest stored report"
	@echo "make scheduler    Start the scheduler in the background"
	@echo "make logs         Follow application logs"
	@echo "make test         Run the test suite"

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

run:
	docker compose run --rm finai python -m main run

send-report:
	docker compose run --rm finai python -m main send-report

scheduler:
	docker compose up -d

logs:
	docker compose logs -f finai

test:
	.venv/Scripts/python.exe -m pytest -q
