# Repository Guidelines

## Project Structure & Module Organization

The application is a Python 3.11+ service under `src/`. Keep each concern in
its existing boundary:

- `src/ingestion/` collects B3 prices and Google News RSS entries.
- `src/agents/` contains the LangGraph workflow and validated LLM schemas.
- `src/agents/prompt/` contains YAML prompts rendered with LangChain
  `ChatPromptTemplate`.
- `src/database/` owns SQLAlchemy models, sessions, and database bootstrap.
- `src/delivery/` contains report channels, currently SMTP email.
- `src/main.py` is the CLI and scheduler entry point; `src/settings.py` reads
  environment configuration.
- `infra/` owns Infrastructure-as-Code (Terraform) and automation scripts for
  GCP deployment under the Always Free tier (`infra/terraform/`, `infra/scripts/`).
- `specs/` holds technical and infrastructure specifications.
- `tests/` contains pytest tests. Add test files as `test_<area>.py`.
- `docs/` holds product and technical documentation; do not place runtime code
  there.


## Build, Test, and Development Commands

Create a virtual environment and install dependencies before local work:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e . --no-deps
pytest -q
python -m main run
```

`python -m main run` performs one collection and analysis cycle. Use
`python -m main send-report` to send the newest stored report. For the complete
stack, copy `.env.example` to `.env`, configure secrets, then run
`docker compose up --build`.

For Docker manual runs, use `docker compose run --rm finai python -m main run`,
`docker compose run --rm finai python -m main send-report`, or
`docker compose run --rm finai python -m main scheduler --run-now`.

To validate Terraform infrastructure configurations:

```powershell
cd infra/terraform
terraform fmt -check
terraform init -backend=false
terraform validate
```

GitHub Actions uses `ci.yml` for PR checks (testing Python and validating
Terraform), `publish-image.yml` to publish SHA-tagged images to GHCR after
merges to `main`, and `deploy-production.yml` for deploying to the GCP
Compute Engine VM via SSH and Docker Compose. Never add credentials to workflow
files or Docker build arguments.


## Coding Style & Naming Conventions

Use four-space indentation, type hints for public functions, and concise
docstrings for modules or non-obvious classes. Follow PEP 8: `snake_case` for
functions, modules, and variables; `PascalCase` for classes; `UPPER_CASE` for
constants. Keep external API calls in `ingestion/`, `agents/`, or `delivery/`;
do not add them directly to `main.py`. No formatter or linter is configured,
so run `python -m compileall -q src tests` before submitting changes.

## Testing Guidelines

Use pytest and test observable behavior, especially JSON validation, error
isolation per ticker, and persistence boundaries. Avoid live calls to Groq,
OpenAI, yfinance, RSS, SMTP, or PostgreSQL in unit tests; mock those clients.
Name tests `test_<behavior>` and run `pytest -q` locally. Add a regression test
for every bug fix where practical.

Keep prompt text in `src/agents/prompt/*.yaml`; load it through the existing
prompt helper and render it with `ChatPromptTemplate` instead of embedding
prompt prose in Python.

## Secrets and Environment Files

Never open, read, print, quote, inspect, or otherwise retrieve `.env` or any
other file containing secrets. Never expose API keys, passwords, tokens, SMTP
credentials, database credentials, or full secret-bearing environment values in
chat, logs, diagnostics, test output, patches, or reports. Use `.env.example`
and explicitly supplied placeholder values for configuration checks. If a
secret appears in user-provided output, redact it and instruct the user to
rotate it; do not repeat or validate the secret.

## Integration Pitfalls

- Prices use `yfinance` with a Brapi fallback; news comes from Google News RSS
  and is limited to the previous 24 hours.
- The LangGraph workflow has `research` and `analyse` nodes. LLM output must
  remain valid JSON accepted by `TickerAnalysis`.
- PostgreSQL is provided by Docker Compose and bootstrap uses SQLAlchemy
  `create_all`; there are no schema migrations.
- Scheduler times use `America/Sao_Paulo`: collection at 18:00 and email at
  08:00 on weekdays. B3 holidays are not handled.
- `get_settings()` is cached, so environment changes require a new process.
- `docs/PRD_FinAI_BR.md` is the source for product requirements; link to it
  instead of duplicating its content here.
- GCP deployment uses an `e2-micro` VM in `us-central1` (Always Free tier) with a
  30 GB `pd-standard` disk and a 2 GB swapfile. `docker-compose.prod.yml` runs
  both PostgreSQL and the FinAI container on the host. Production secrets reside
  exclusively in `/opt/finai/.env` on the host and in GitHub Actions environment
  secrets (`production`).


## Commit & Pull Request Guidelines

The repository currently has only an `Initial commit`, so no established
commit convention exists. Use short imperative messages such as
`feat: add RSS retry handling` or `fix: validate empty LLM response`. Pull
requests should explain the behavior change, list commands run, link relevant
issues, and identify configuration or schema changes. Never commit `.env`, API
keys, SMTP passwords, or database dumps.
