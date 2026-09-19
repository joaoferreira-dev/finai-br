provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# Dedicated service account with least privilege for the Compute Engine instance
resource "google_service_account" "finai" {
  account_id   = "finai-vm-sa"
  display_name = "FinAI VM Service Account"
  description  = "Least-privilege service account for FinAI-BR Compute Engine instance"
}

resource "google_project_iam_member" "logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.finai.email}"
}

resource "google_project_iam_member" "monitoring" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.finai.email}"
}

# Firewall rule: restrict SSH access to authorized CIDR blocks
resource "google_compute_firewall" "allow_ssh" {
  name        = "finai-allow-ssh"
  network     = "default"
  description = "Allows SSH access to FinAI-BR instance from authorized CIDRs"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = var.allowed_ssh_cidrs
  target_tags   = ["finai-server"]
}

# Compute Engine Instance (Always Free Tier eligible: e2-micro, 30GB pd-standard, us-central1)
resource "google_compute_instance" "finai" {
  name         = var.instance_name
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["finai-server"]

  boot_disk {
    initialize_params {
      image = var.boot_image
      size  = var.disk_size_gb
      type  = var.disk_type
    }
  }

  network_interface {
    network = "default"

    # Ephemeral public IP assignment (free while instance is running)
    access_config {}
  }

  metadata = {
    ssh-keys               = "${var.admin_ssh_user}:${var.admin_ssh_public_key}"
    block-project-ssh-keys = "true"
  }

  metadata_startup_script = file("${path.module}/../scripts/startup.sh")

  service_account {
    email  = google_service_account.finai.email
    scopes = ["logging-write", "monitoring-write"]
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    preemptible         = false
  }

  lifecycle {
    ignore_changes = [
      metadata["ssh-keys"],
    ]
  }
}
