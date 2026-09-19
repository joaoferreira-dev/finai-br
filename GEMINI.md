# Gemini Guidelines for FinAI-BR

This file provides project-level instructions and context for Gemini and AI assistants working in this repository. Follow these guidelines in conjunction with [AGENTS.md](file:///C:/Users/joaob/OneDrive/Documentos/Code/AI/finai-br/AGENTS.md).

---

## 1. Project Overview & Architecture

FinAI-BR is an autonomous Python 3.11+ financial analysis service tracking 5 high-liquidity B3 equities: `PETR4`, `BBAS3`, `VALE3`, `ITUB4`, and `CSMG3`.

### Concern Boundaries:
- `src/ingestion/`: Market data (`yfinance` with `Brapi` fallback) and Google News RSS collection (previous 24 hours).
- `src/agents/`: Multi-agent orchestration via LangGraph (Researcher and Financial Analyst agents).
- `src/agents/prompt/`: YAML prompts loaded and formatted with LangChain `ChatPromptTemplate`. **Never embed prompt prose in Python files.**
- `src/database/`: PostgreSQL models, sessions, and database bootstrap.
- `src/delivery/`: Report generation and SMTP email dispatch.
- `src/main.py`: CLI and scheduler entry point (`APScheduler`).
- `src/settings.py`: Environment configuration via Pydantic (`get_settings()` is `@lru_cache` memoized).
- `infra/`: Infrastructure-as-Code for Google Cloud Platform (GCP) Always Free Tier:
  - `infra/terraform/`: Terraform configuration for an `e2-micro` VM in `us-central1` with a 30 GB `pd-standard` disk and security firewall rules.
  - `infra/scripts/`: VM bootstrap (`startup.sh`: 2 GB swap, Docker Engine, Compose plugin) and local deploy script (`deploy-local.sh`).
- `specs/`: Technical specifications and architectural plans (`specs/infra_spec.md`).
- `tests/`: Pytest suite (`test_<area>.py`).
- `docs/`: Product documentation (`docs/PRD_FinAI_BR.md`).

---

## 2. Key Commands & Workflows

### Local Development & Testing:
```powershell
# Compile check (mandatory before submitting changes)
python -m compileall -q src tests

# Run unit tests
pytest -q

# Run single market collection & analysis cycle
python -m main run

# Send latest stored report via email
python -m main send-report

# Run scheduler with immediate initial execution
python -m main scheduler --run-now
```

### Infrastructure Validation:
```powershell
cd infra/terraform
terraform fmt -check
terraform init -backend=false
terraform validate
```

### Docker Commands:
```powershell
# Local stack (db + app)
docker compose up --build

# Run manual cycle in container
docker compose run --rm finai python -m main run
```

---

## 3. Coding Style & Conventions

- **Python:** PEP 8, 4-space indentation, type hints on public functions, concise docstrings.
- **External Calls:** Keep network calls restricted to `ingestion/`, `agents/`, or `delivery/`; never place them directly in `main.py`.
- **Prompts:** Store prompts exclusively in `src/agents/prompt/*.yaml`.
- **Testing:** Mock external clients (Groq, OpenAI, yfinance, RSS, SMTP, PostgreSQL) in unit tests. Test observable behavior and error isolation per ticker.
- **Terraform:** Format with `terraform fmt`, maintain minimal privilege IAM, and preserve GCP Always Free constraints.

---

## 4. Security & Secrets Management

- **Absolute Rule:** NEVER read, inspect, print, quote, or commit `.env` or any secret-bearing files.
- **Reference Templates:** Refer only to `.env.example` and `infra/terraform/terraform.tfvars.example`.
- **Production Secrets:** Production credentials reside exclusively in `/opt/finai/.env` on the deployed host and in GitHub Actions environment secrets (`production`).
- If secrets appear in user output or logs, redact immediately and advise key rotation.

---

## 5. GCP Free-Tier Deployment Guardrails

- Target machine: `e2-micro` (Always Free eligible in `us-central1`, `us-east1`, `us-west1`).
- Disk: Maximum 30 GB `pd-standard` (standard persistent disk; do not use `pd-ssd` or `pd-balanced`).
- Memory: Always configure a 2 GB swapfile on the VM to ensure memory stability for Docker, PostgreSQL, and Python.
- Database: Run PostgreSQL via Docker Compose on the VM (`docker-compose.prod.yml`) to maintain zero monthly infrastructure cost.