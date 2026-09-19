output "instance_name" {
  description = "Name of the Compute Engine instance."
  value       = google_compute_instance.finai.name
}

output "instance_zone" {
  description = "Zone where the instance is located."
  value       = google_compute_instance.finai.zone
}

output "instance_public_ip" {
  description = "Public IP address of the instance (use as PROD_SSH_HOST in GitHub Actions)."
  value       = google_compute_instance.finai.network_interface[0].access_config[0].nat_ip
}

output "ssh_connection_command" {
  description = "Convenience SSH command to connect to the instance."
  value       = "ssh ${var.admin_ssh_user}@${google_compute_instance.finai.network_interface[0].access_config[0].nat_ip}"
}

output "service_account_email" {
  description = "Email of the service account attached to the instance."
  value       = google_service_account.finai.email
}
