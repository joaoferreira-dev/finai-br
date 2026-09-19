# Specification: GCP Infrastructure for FinAI-BR (Zero/Minimal Cost)

**Document Version:** 1.0  
**Status:** Approved for Implementation  
**Target Platform:** Google Cloud Platform (GCP)  
**Primary Objective:** Deploy FinAI-BR with $0.00 (or near-zero) monthly operating cost using GCP Always Free Tier.

---

## 1. Executive Summary & Application Analysis

FinAI-BR is an autonomous financial market analysis service focusing on 5 key B3 tickers (`PETR4`, `BBAS3`, `VALE3`, `ITUB4`, `CSMG3`).

### 1.1. Workload Characteristics
- **Batch Cadence:**
  - **18:00 BRT (Mon–Fri):** Market data ingestion (`yfinance` / `Brapi`), Google News RSS collection (last 24h), LangGraph multi-agent analysis (Researcher + Analyst using Groq/OpenAI), and persistence into PostgreSQL. Typical duration: **30–90 seconds**.
  - **08:00 BRT (Mon–Fri):** Consolidate latest analysis from PostgreSQL, render HTML report, and deliver via SMTP email. Typical duration: **5–15 seconds**.
  - **Off-hours / Weekends:** Complete idle.
- **Resource Footprint:**
  - **PostgreSQL 16:** ~30–50 MB RAM idle, peaks at ~80 MB during writes. Data storage: < 50 MB/year for 5 tickers.
  - **FinAI Runner (Python 3.11):** ~80–150 MB RAM during LangGraph workflow execution.
  - **Total System RAM Footprint:** < 250 MB RAM active, < 80 MB idle.

---

## 2. GCP Cost & Architecture Analysis

To achieve a **$0.00 / free-tier or minimal-cost** deployment, we evaluated two distinct architectural approaches against GCP pricing and free tiers.

### 2.1. Comparison Matrix

| Dimension | Architecture A: Always Free Compute Engine VM (`e2-micro`) | Architecture B: Serverless (Cloud Run Jobs + Cloud Scheduler) |
| :--- | :--- | :--- |
| **Compute Cost** | **$0.00 / month** (1 free `e2-micro` instance in `us-central1`, `us-east1`, or `us-west1`) | **$0.00 / month** (Cloud Run free tier: 360k vCPU-s / mo; workload consumes ~2.6k vCPU-s / mo) |
| **Scheduler Cost** | **$0.00** (Built-in APScheduler or system cron on VM) | **$0.00** (Cloud Scheduler free tier: 3 free jobs / mo) |
| **Database Cost** | **$0.00** (Self-hosted `postgres:16-alpine` on VM disk) | **~$8–12 / month** if using Cloud SQL (no free tier), OR **$0.00** if using external free tier (e.g., Supabase / Neon) |
| **Storage Cost** | **$0.00** (30 GB `pd-standard` disk included in Always Free) | **$0.00–$0.10** (Artifact Registry image storage > 0.5 GB) |
| **Network Egress**| **$0.00** (1 GB / month free egress to worldwide) | **$0.00** |
| **Compatibility** | **100% Native:** Directly reuses existing `docker-compose.prod.yml` and `.github/workflows/deploy-production.yml` | Requires restructuring database connection, Cloud SQL Auth Proxy, and modifying deployment pipelines |
| **Estimated Total Cost** | **$0.00 / month (100% Free)** | **$0.00 / month** (with external free DB) or **~$10 / month** (with Cloud SQL) |

### 2.2. Recommended Architecture: Architecture A (e2-micro Always Free VM)

**Architecture A is selected as the primary solution** because:
1. **True $0.00 Cost:** Covers compute, database, scheduler, and persistent storage entirely within the GCP Always Free Tier quotas without requiring external third-party DB providers or paid Cloud SQL instances.
2. **Zero Architecture Drift:** FinAI-BR already provides `docker-compose.prod.yml` and a ready-to-use GitHub Actions workflow (`deploy-production.yml`) configured for SSH deployment on Docker hosts.
3. **Low Complexity & High Reliability:** No cross-service network latency between Cloud Run and external databases; PostgreSQL data resides safely on a persistent 30 GB standard disk.

*(Note: The Terraform codebase will also include configuration guidelines for Architecture B as an alternative for users preferring fully managed serverless deployments with external database services like Neon/Supabase).*

---

## 3. Detailed Architecture Design (Architecture A)

### 3.1. Infrastructure Components (GCP)
```
                  ┌────────────────────────────────────────────────────────┐
                  │                      Google Cloud                      │
                  │             Region: us-central1 (Always Free)          │
                  │                                                        │
                  │  ┌──────────────────────────────────────────────────┐  │
                  │  │ VPC Network & Firewall Rules                     │  │
                  │  │ - Allow SSH (port 22) via IAP / Admin IP only   │  │
                  │  │ - Deny public access to Postgres (port 5432)     │  │
                  │  │ - Allow outbound HTTPS (B3 data, Groq/OpenAI,    │  │
                  │  │   SMTP, RSS feeds)                               │  │
                  │  └───────────────────────┬──────────────────────────┘  │
                  │                          │                             │
                  │  ┌───────────────────────▼──────────────────────────┐  │
                  │  │ Compute Engine VM: e2-micro                      │  │
                  │  │ - OS: Ubuntu 22.04 LTS                           │  │
                  │  │ - 1 vCPU (burstable), 1 GB RAM                   │  │
                  │  │ - 30 GB Persistent Disk (pd-standard, Free Tier) │  │
                  │  │ - 2 GB Linux Swapfile (enables RAM headroom)     │  │
                  │  │                                                  │  │
                  │  │  ┌────────────────────────────────────────────┐  │  │
                  │  │  │ Docker & Docker Compose Engine             │  │  │
                  │  │  │                                            │  │  │
                  │  │  │  ┌────────────────┐   ┌─────────────────┐  │  │  │
                  │  │  │  │ Container: db  │   │ Container:      │  │  │  │
                  │  │  │  │ postgres:16    │◄──┤ finai           │  │  │  │
                  │  │  │  │ (Docker Volume)│   │ (Scheduler/Run) │  │  │  │
                  │  │  │  └────────────────┘   └────────┬────────┘  │  │  │
                  │  │  └────────────────────────────────┼───────────┘  │  │
                  │  └───────────────────────────────────┼──────────────┘  │
                  └──────────────────────────────────────┼─────────────────┘
                                                         │
                        External APIs                    ▼
                  ┌────────────────────────────────────────────────────────┐
                  │ • Groq / OpenAI LLM APIs                               │
                  │ • yfinance / Brapi API                                 │
                  │ • Google News RSS Feeds                                │
                  │ • SMTP Mail Server (Gmail / SendGrid / Custom)         │
                  └────────────────────────────────────────────────────────┘
```

### 3.2. Hardware Sizing & Memory Management on `e2-micro`
The `e2-micro` instance provides 1 GB of physical memory. Python with LangChain and PostgreSQL requires stable memory allocation to prevent Out-Of-Memory (OOM) kills during daily analysis cycles.
- **2 GB Swapfile:** Automatically provisioned on the 30 GB persistent disk during VM initialization via `startup.sh`.
- **Kernel Tuning:**
  - `vm.swappiness = 10` (prefers physical RAM, swaps only when memory pressure rises).
  - `vm.vfs_cache_pressure = 50` (maintains filesystem dentries/inodes in cache).

### 3.3. Networking & Security
- **No Public DB Exposure:** PostgreSQL port `5432` is bound only to Docker internal network (`finai_default`); it is never exposed on the VM's public IP.
- **Firewall Rules:**
  - `finai-allow-ssh`: Port 22 restricted to specific administrator IP CIDR or GCP Identity-Aware Proxy (`35.235.240.0/20`).
  - Outbound traffic enabled for HTTPS (port 443) and SMTP (port 587/465).
- **Service Account & IAM:**
  - Dedicated service account with minimal roles (`logging.logWriter`, `monitoring.metricWriter`).
- **Secrets Management:**
  - Production `.env` is securely copied to the VM host (`${PROD_APP_DIR}/.env`) and never committed to Git, matching the repository guidelines.

---

## 4. Planned `infra/` Directory Structure

The infrastructure will be organized inside the new `infra/` directory as follows:

```
infra/
├── README.md                      # Complete guide for provisioning and operational management
├── scripts/
│   ├── startup.sh                 # Cloud-init / instance startup script (Docker, Swap, Directory setup)
│   └── deploy-local.sh            # Optional manual deployment script from local machine
└── terraform/
    ├── main.tf                    # GCP Provider, Compute Instance, Disk, and Firewall configuration
    ├── variables.tf               # Configurable variables (project_id, region, zone, ssh_keys, etc.)
    ├── outputs.tf                 # Useful outputs (instance public IP, SSH command, status)
    ├── versions.tf                # Terraform and GCP provider versions
    ├── terraform.tfvars.example   # Example values for environment configuration
    └── budget.tf                  # Optional GCP Cloud Billing Budget Alert ($0.01 threshold)
```

---

## 5. Configuration & Variables Specification

### 5.1. Terraform Variables (`infra/terraform/variables.tf`)

| Variable Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `project_id` | `string` | *(Required)* | GCP Project ID |
| `region` | `string` | `"us-central1"` | GCP Region eligible for Always Free (`us-central1`, `us-east1`, `us-west1`) |
| `zone` | `string` | `"us-central1-a"` | GCP Zone |
| `instance_name` | `string` | `"finai-prod-vm"` | Name of the Compute Engine instance |
| `machine_type` | `string` | `"e2-micro"` | Machine type (Always Free tier eligible) |
| `disk_size_gb` | `number` | `30` | Boot disk size in GB (30 GB standard persistent disk is Always Free) |
| `disk_type` | `string` | `"pd-standard"` | Disk type (`pd-standard` qualifies for Always Free) |
| `admin_ssh_public_key` | `string` | *(Required)* | Public SSH key for accessing the instance and CI/CD deployment |
| `admin_ssh_user` | `string` | `"finai"` | Linux user created on the instance |
| `allowed_ssh_cidrs` | `list(string)` | `["0.0.0.0/0"]` | CIDR blocks allowed to connect via SSH (can be narrowed to admin IP or IAP) |

### 5.2. Startup Script Tasks (`infra/scripts/startup.sh`)
1. Update system packages (`apt-get update`).
2. Configure 2 GB swapfile at `/swapfile` and set `vm.swappiness = 10`.
3. Install Docker Engine, containerd, and Docker Compose plugin (`docker-compose-v2`).
4. Add the configured admin user to the `docker` group.
5. Create application directory at `/opt/finai` with proper ownership.
6. Install log rotation for Docker container logs.

---

## 6. GitHub Actions CI/CD Deployment Workflow for GCP

The project utilizes GitHub Actions for automated testing, image publication, and deployment. The production deployment workflow connects directly to the GCP Compute Engine instance.

### 6.1. Deployment Pipeline Architecture

```
  [git push / merge to main]
             │
             ▼
  ┌────────────────────────┐
  │ GitHub Actions:        │
  │ publish-image.yml      │  Builds Docker image & tags with commit SHA:
  │                        │  ghcr.io/<repo>:sha-<sha>
  └──────────┬─────────────┘
             │ triggers on success (workflow_run)
             ▼
  ┌────────────────────────┐
  │ GitHub Actions:        │
  │ deploy-production.yml  │  1. Authenticates SSH to GCP e2-micro VM
  │                        │  2. Uploads updated docker-compose.prod.yml
  │                        │  3. Logs into GHCR on the GCP VM
  │                        │  4. Pulls sha-<sha> image & re-launches containers
  └──────────┬─────────────┘
             │ SSH (Port 22)
             ▼
  ┌────────────────────────┐
  │ GCP Compute Engine VM  │
  │ (finai-prod-vm)        │  Executes: docker compose pull && up -d
  └────────────────────────┘
```

### 6.2. Workflow Specification (`.github/workflows/deploy-production.yml`)

The production deploy workflow is defined as:

```yaml
name: Deploy production

on:
  workflow_run:
    workflows: [Publish Docker image]
    types: [completed]
    branches: [main]

concurrency:
  group: production
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  deploy:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    environment: production
    env:
      IMAGE: ghcr.io/${{ github.repository }}:sha-${{ github.event.workflow_run.head_sha }}
      APP_DIR: ${{ secrets.PROD_APP_DIR }}
    steps:
      - name: Checkout deployed revision
        uses: actions/checkout@v4
        with:
          ref: ${{ github.event.workflow_run.head_sha }}

      - name: Install SSH key
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.PROD_SSH_KEY }}

      - name: Trust production host
        run: ssh-keyscan -H "${{ secrets.PROD_SSH_HOST }}" >> ~/.ssh/known_hosts

      - name: Upload production Compose file
        run: |
          ssh "${{ secrets.PROD_SSH_USER }}@${{ secrets.PROD_SSH_HOST }}" "mkdir -p '$APP_DIR'"
          scp docker-compose.prod.yml "${{ secrets.PROD_SSH_USER }}@${{ secrets.PROD_SSH_HOST }}:${APP_DIR}/docker-compose.prod.yml"

      - name: Deploy image on GCP VM
        env:
          GHCR_USERNAME: ${{ secrets.GHCR_DEPLOY_USERNAME }}
          GHCR_TOKEN: ${{ secrets.GHCR_DEPLOY_TOKEN }}
        run: |
          printf '%s' "$GHCR_TOKEN" | ssh "${{ secrets.PROD_SSH_USER }}@${{ secrets.PROD_SSH_HOST }}" \
            "docker login ghcr.io -u '$GHCR_USERNAME' --password-stdin && \
             mkdir -p '$APP_DIR' && \
             printf 'FINAI_IMAGE=$IMAGE\n' > '$APP_DIR/.image.env' && \
             docker compose --env-file '$APP_DIR/.image.env' -f '$APP_DIR/docker-compose.prod.yml' pull && \
             docker compose --env-file '$APP_DIR/.image.env' -f '$APP_DIR/docker-compose.prod.yml' up -d --remove-orphans && \
             docker compose --env-file '$APP_DIR/.image.env' -f '$APP_DIR/docker-compose.prod.yml' ps"
```

### 6.3. Required GitHub Secrets & Environment Variables

Configure these secrets in GitHub repository **Settings -> Environments -> production**:

| Secret Name | Source / Value | Description |
| :--- | :--- | :--- |
| `PROD_SSH_HOST` | Terraform output: `instance_public_ip` | External IP address of the GCP `e2-micro` VM |
| `PROD_SSH_USER` | `finai` (configured in `variables.tf`) | Non-root Linux user on the GCP VM |
| `PROD_SSH_KEY` | Private SSH key (PEM / OpenSSH format) | Private key paired with `admin_ssh_public_key` |
| `PROD_APP_DIR` | `/opt/finai` | Directory on the GCP VM hosting Compose and `.env` |
| `GHCR_DEPLOY_USERNAME` | GitHub username / bot account | Account with read access to repository packages |
| `GHCR_DEPLOY_TOKEN` | Personal Access Token (`read:packages`) | Token allowing the GCP VM to pull private images |

### 6.4. Initial VM Setup & Deployment Checklist
1. **Provision Infrastructure:** Run `terraform apply` inside `infra/terraform/` to spin up the GCP VM and network.
2. **Retrieve Outputs:** Copy the generated `instance_public_ip` and SSH configuration.
3. **Seed Production `.env` on GCP:** SSH into the VM and populate `/opt/finai/.env` with production secrets (database URL, Groq/OpenAI keys, SMTP credentials).
4. **Configure GitHub Secrets:** Enter the 6 secrets in the GitHub `production` environment.
5. **Trigger Deployment:** Push or merge to `main` branch. GitHub Actions will build, test, publish the image, and trigger the remote deployment on GCP.

### 6.5. CI Workflow Integration: Terraform Lint, Validate & Plan (`.github/workflows/ci.yml`)

To catch infrastructure syntax regressions, styling violations, and configuration drift before merging, a dedicated `terraform` job will be added to the pull request CI workflow ([`.github/workflows/ci.yml`](file:///C:/Users/joaob/OneDrive/Documentos/Code/AI/finai-br/.github/workflows/ci.yml)).

#### 6.5.1. Job Stages
1. **Format Check (`terraform fmt -check`):** Verifies code adheres to canonical Terraform style.
2. **Initialization (`terraform init -backend=false`):** Installs required provider plugins without requiring remote backend access.
3. **Validation (`terraform validate`):** Validates syntax, resource references, and schema correctness.
4. **Terraform Plan (`terraform plan`):** Generates an execution plan to verify that all resource arguments and dependencies resolve cleanly.
   - **With GCP Credentials (`GCP_SA_KEY` or Workload Identity):** Authenticates to GCP and generates a live speculative plan against the project.
   - **Without GCP Credentials (CI Fallback):** Executes schema validation and format verification, ensuring PRs pass even prior to GCP account onboarding.

#### 6.5.2. Proposed Workflow Addition (`.github/workflows/ci.yml`)

```yaml
  terraform:
    name: Terraform Quality & Plan
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: infra/terraform
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9.0"

      - name: Terraform Format Check
        run: terraform fmt -check -diff

      - name: Terraform Init
        run: terraform init -backend=false

      - name: Terraform Validate
        run: terraform validate

      - name: Authenticate to GCP (Optional for Live Plan)
        if: ${{ env.GCP_SA_KEY != '' }}
        uses: google-github-actions/auth@v2
        env:
          GCP_SA_KEY: ${{ secrets.GCP_SA_KEY }}
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}

      - name: Terraform Plan
        if: ${{ env.GCP_SA_KEY != '' }}
        env:
          GCP_SA_KEY: ${{ secrets.GCP_SA_KEY }}
        run: |
          terraform plan \
            -var="project_id=${{ secrets.GCP_PROJECT_ID }}" \
            -var="admin_ssh_public_key=${{ secrets.PROD_SSH_PUBLIC_KEY }}" \
            -input=false
```

---

## 7. Cost Safeguards & Monitoring

To guarantee that costs remain at **$0.00** and avoid surprise billing:
1. **Resource Guardrails:**
   - Single `e2-micro` instance.
   - Max 30 GB `pd-standard` (not `pd-ssd` or `pd-balanced`, as only `pd-standard` is Always Free).
   - Region restricted to `us-central1`, `us-east1`, or `us-west1`.
2. **GCP Cloud Billing Budget Alert:**
   - Terraform can include a Google Cloud Billing Budget alert set to trigger an email alert if charges reach **$0.01**.
3. **Log Retention:**
   - Docker container log limits (`max-size: 10m`, `max-file: 3`) to prevent disk bloat.

---

## 8. Verification & Acceptance Criteria

1. **Terraform Plan & Validation:** Terraform configuration validates cleanly with `terraform validate` and displays plan without errors.
2. **VM Bootstrap Verification:**
   - VM starts and runs Docker daemon.
   - Swapfile is active (`free -h` shows ~2 GB swap).
3. **FinAI Workflow Verification:**
   - Execution of `docker compose run --rm finai python -m main run` executes the 5-ticker analysis and writes records to the `db` container.
   - Execution of `docker compose run --rm finai python -m main send-report` sends the report email.
4. **Zero Cost Assurance:**
   - Verify all chosen resources strictly conform to GCP Always Free Tier documentation.
