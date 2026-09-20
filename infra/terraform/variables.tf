variable "project_id" {
  description = "The GCP Project ID where resources will be provisioned."
  type        = string
}

variable "region" {
  description = "The GCP region. Must be us-central1, us-east1, or us-west1 to qualify for Always Free tier."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "The GCP zone within the selected region."
  type        = string
  default     = "us-central1-a"
}

variable "instance_name" {
  description = "Name of the Compute Engine instance."
  type        = string
  default     = "finai-prod-vm"
}

variable "machine_type" {
  description = "Compute Engine machine type. e2-micro qualifies for GCP Always Free tier."
  type        = string
  default     = "e2-micro"
}

variable "disk_size_gb" {
  description = "Boot disk size in GB. 30 GB standard persistent disk qualifies for GCP Always Free tier."
  type        = number
  default     = 30
}

variable "disk_type" {
  description = "Disk type. pd-standard qualifies for GCP Always Free tier (do not use pd-ssd or pd-balanced for zero cost)."
  type        = string
  default     = "pd-standard"
}

variable "boot_image" {
  description = "OS Image family and project."
  type        = string
  default     = "ubuntu-os-cloud/ubuntu-2204-lts"
}

variable "admin_ssh_user" {
  description = "Non-root Linux username created on the instance for deployment and maintenance."
  type        = string
  default     = "finai"
}

variable "admin_ssh_public_key" {
  description = "Public SSH key for admin access and GitHub Actions CI/CD deployment (e.g., 'ssh-ed25519 AAAAC3... user@host')."
  type        = string
}

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks permitted to connect to SSH (port 22). Set to your own public IP, or 35.235.240.0/20 for GCP IAP, or 0.0.0.0/0."
  type        = list(string)
  validation {
    condition     = !contains(var.allowed_ssh_cidrs, "0.0.0.0/0")
    error_message = "Do not expose SSH globally; use a specific administrator CIDR or the GCP IAP range."
  }
}
