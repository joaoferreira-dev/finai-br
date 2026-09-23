# FinAI-BR agent instructions

## Project map
- Python 3.11+ service; source is in `src/`, tests in `tests/`.
- `src/ingestion/`: B3 prices and Google News RSS; yfinance falls back to Brapi.
- `src/agents/`: two-node LangGraph workflow, schemas, and YAML prompts.
- `src/database/`: SQLAlchemy models, sessions, PostgreSQL bootstrap.
- `src/delivery/`: HTML/text reports and SMTP email.
- `src/main.py`: CLI and weekday scheduler; `src/settings.py`: configuration.
- `infra/`: Terraform, GCP operations, and deployment scripts; `docs/`: product/incident docs.

## Common commands
Install locally: `python -m pip install -r requirements.txt`, then `python -m pip install -e . --no-deps`.
Run checks: `python -m compileall -q src tests` and `pytest -q`.
Local Docker: `docker compose up --build`; run one analysis with `docker compose run --rm finai python -m main run`, send the latest report with `docker compose run --rm finai python -m main send-report`.
Use `make help` for other local Docker targets.
Production runs on a GCP Compute Engine VM with Docker Compose. The deployed image is selected by `/opt/finai/.image.env`; one-off production commands must include `--env-file .image.env -f docker-compose.prod.yml`. Do not read the production `.env`.
Terraform checks: from `infra/terraform`, run `terraform fmt -check`, `terraform init -backend=false`, and `terraform validate`.

## Product and implementation rules
- The scheduler uses `America/Sao_Paulo`: collect/analyse weekdays at 18:00; send the latest report weekdays at 06:00. B3 holidays are not handled.
- Market history uses adjusted closes and trading sessions; missing inputs stay unavailable. Each analysis stores its market snapshot in `Analysis.market_context_json`; bootstrap adds nullable columns idempotently, with no migration framework or historical backfill.
- Keep provider/API calls in ingestion, agents, or delivery modules, not `main.py`. Preserve the two-node workflow and validated `TickerAnalysis` JSON schema.
- Keep prompt prose in `src/agents/prompt/*.yaml`, loaded by the existing helper and rendered through `ChatPromptTemplate`.
- `get_settings()` is cached; configuration changes require a new process.
- See [PRD](docs/PRD_FinAI_BR.md) for product requirements and [infrastructure guide](infra/README.md) for deployment details.

## Quality and safety
- Follow PEP 8, four-space indentation, type hints on public functions, and concise docstrings where useful. Add focused regression tests for behavior changes; mock Groq/OpenAI, yfinance/Brapi/RSS, SMTP, and PostgreSQL in unit tests.
- Never open, read, print, quote, or inspect `.env` or other secret-bearing files. Never expose credentials or full secret-bearing environment values. Use `.env.example` and placeholders for configuration checks. Do not commit secrets or database dumps.
- CI runs compile/tests and Docker/Terraform checks for feature/fix pushes and PRs to `main`. Merging to `main` publishes the SHA-tagged image; the production workflow deploys it.
- Every commit must end with this exact trailer on its own final line: `Co-authored-by: codex <codex@openai.com>`. Use concise imperative commit subjects. PRs should summarize behavior, checks, linked issues, and config/schema changes.
