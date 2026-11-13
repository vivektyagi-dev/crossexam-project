output "cluster_name" {
  value = google_container_cluster.gke.name
}

output "get_credentials" {
  description = "Run this to point kubectl at the cluster"
  value       = "gcloud container clusters get-credentials ${google_container_cluster.gke.name} --region ${var.region} --project ${var.project_id}"
}

output "documents_bucket" {
  value = google_storage_bucket.documents.name
}

output "artifact_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}"
}

# Paste these two into the GitHub repository's Actions variables.
output "github_wif_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "github_deployer_service_account" {
  value = google_service_account.sa["deployer"].email
}
