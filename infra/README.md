# FinAI-BR Infrastructure (GCP)

This directory contains the Infrastructure-as-Code (IaC) configuration and operational scripts to deploy FinAI-BR onto Google Cloud Platform (GCP) under the **Always Free Tier** ($0.00/month).

---

## 1. Overview & Free Tier Architecture

- **Compute Instance:** 1x `e2-micro` (2 vCPUs burstable, 1 GB RAM) in `us-central1`.
- **Persistent Disk:** 30 GB standard persistent disk (`pd-standard`).
- **Memory Optimization:** 2 GB Linux swapfile (`/swapfile`) configured automatically by `scripts/startup.sh`.
- **Workloads:**
  - `db`: `postgres:16-alpine` with persistent volume.
  - `finai`: Daily analysis (`18:00 BRT`) and HTML report email (`08:00 BRT`).
- **Operating Cost:** **$0.00 / month** under GCP Always Free Tier quotas.

---

## 2. Directory Structure

```
infra/
├── README.md                      # This guide
├── scripts/
│   ├── startup.sh                 # Cloud-init instance bootstrap (Docker, Swap, Directory)
│   └── deploy-local.sh            # Operator script for manual deployment via SSH
└── terraform/
    ├── main.tf                    # GCP VM, disk, and firewall resources
    ├── variables.tf               # Configurable variables
    ├── outputs.tf                 # Useful outputs (public IP, SSH command)
    ├── versions.tf                # Provider and Terraform version constraints
    └── terraform.tfvars.example   # Example variables template
```

---

## 3. Prerequisites

1. [Google Cloud SDK (`gcloud`)](https://cloud.google.com/sdk/docs/install) installed and authenticated:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   gcloud config set project <YOUR_GCP_PROJECT_ID>
   ```
2. Enable required GCP APIs:
   ```bash
   gcloud services enable compute.googleapis.com
   ```
3. [Terraform](https://developer.hashicorp.com/terraform/install) (>= 1.5.0).
4. An SSH key pair for instance administration:
   ```bash
   ssh-keygen -t ed25519 -C "finai-deploy" -f ~/.ssh/finai_gcp
   ```

---

## 4. Provisioning with Terraform

1. Navigate to the terraform directory:
   ```bash
   cd infra/terraform
   ```
2. Create your `terraform.tfvars` from the example:
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```
3. Edit `terraform.tfvars`:
   - Set `project_id` to your GCP Project ID.
   - Paste the contents of `~/.ssh/finai_gcp.pub` into `admin_ssh_public_key`.
4. Initialize and apply:
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```
5. Take note of the output `instance_public_ip`.

---

## 5. First-Time Instance Setup & Secrets

Once the VM is created, the startup script automatically installs Docker, configures 2 GB swap, and creates `/opt/finai`.

1. Connect to the instance:
   ```bash
   ssh -i ~/.ssh/finai_gcp finai@<INSTANCE_PUBLIC_IP>
   ```
2. Create `/opt/finai/.env` with your production secrets:
   ```bash
   cd /opt/finai
   cat << 'EOF' > .env
   DATABASE_URL=postgresql+psycopg://finai:finai@db:5432/finai
   POSTGRES_DB=finai
   POSTGRES_USER=finai
   POSTGRES_PASSWORD=generate_a_secure_password_here
   BRAPI_TOKEN=
   LLM_PROVIDER=groq
   GROQ_API_KEY=your_groq_api_key_here
   GROQ_MODEL=openai/gpt-oss-20b
   OPENAI_API_KEY=
   OPENAI_MODEL=gpt-4o-mini
   EMAIL_ENABLED=true
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your_email@gmail.com
   SMTP_PASSWORD=your_app_password
   EMAIL_FROM=your_email@gmail.com
   EMAIL_TO=recipient@example.com
   EOF
   chmod 600 .env
   ```
3. Verify swap and Docker status:
   ```bash
   free -h
   docker --version
   docker compose version
   ```

---

## 6. GitHub Actions Automated Deployment

To enable automated deployments upon merging to `main`:

1. In your GitHub repository, go to **Settings -> Environments -> New environment** and name it `production`.
2. Add the following **Environment secrets**:
   - `PROD_SSH_HOST`: `<INSTANCE_PUBLIC_IP>` (from Terraform output)
   - `PROD_SSH_USER`: `finai`
   - `PROD_SSH_KEY`: The private key contents (`~/.ssh/finai_gcp`)
   - `PROD_APP_DIR`: `/opt/finai`
   - `GHCR_DEPLOY_USERNAME`: Your GitHub username
   - `GHCR_DEPLOY_TOKEN`: A GitHub Personal Access Token with `read:packages` scope.
3. Every merge to `main` will build the Docker image, push it to GHCR, and deploy it to the GCP instance.

---

## 7. Operational & Maintenance Commands

From your local machine or directly on the instance:

- **Check container status:**
  ```bash
  ssh -i ~/.ssh/finai_gcp finai@<INSTANCE_PUBLIC_IP> "cd /opt/finai && docker compose -f docker-compose.prod.yml ps"
  ```
- **View live application logs:**
  ```bash
  ssh -i ~/.ssh/finai_gcp finai@<INSTANCE_PUBLIC_IP> "cd /opt/finai && docker compose -f docker-compose.prod.yml logs -f finai"
  ```
- **Trigger an immediate run manually:**
  ```bash
  ssh -i ~/.ssh/finai_gcp finai@<INSTANCE_PUBLIC_IP> "cd /opt/finai && docker compose -f docker-compose.prod.yml run --rm finai python -m main run"
  ```
- **Send report email immediately:**
  ```bash
  ssh -i ~/.ssh/finai_gcp finai@<INSTANCE_PUBLIC_IP> "cd /opt/finai && docker compose -f docker-compose.prod.yml run --rm finai python -m main send-report"
  ```
