# Pods authenticate as their Kubernetes service account (Workload Identity Federation for GKE):
# roles are granted straight to each KSA, so there are no runtime keys and no Google service
# accounts to link. Only the nodes and the GitHub deployer have Google service accounts.

resource "google_service_account" "sa" {
  for_each     = toset(["nodes", "deployer"])
  account_id   = "${local.name}-${each.key}"
  display_name = "crossexam ${each.key}"
}

# ---------------------------------------------------------------- nodes (least privilege)
resource "google_project_iam_member" "nodes" {
  project = var.project_id
  role    = "roles/container.defaultNodeServiceAccount"
  member  = "serviceAccount:${google_service_account.sa["nodes"].email}"
}

resource "google_artifact_registry_repository_iam_member" "nodes_pull" {
  repository = google_artifact_registry_repository.repo.name
  location   = var.region
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.sa["nodes"].email}"
}

# ---------------------------------------------------------------- pods
locals {
  # KSA names come from infra/k8s/base/serviceaccounts.yaml.
  runtime_ksas = ["api", "reader", "agent"]
  ksa = {
    for c in local.runtime_ksas : c =>
    "principal://iam.googleapis.com/projects/${data.google_project.this.number}/locations/global/workloadIdentityPools/${var.project_id}.svc.id.goog/subject/ns/${local.namespace}/sa/${local.name}-${c}"
  }
  runtime_roles = [
    "roles/cloudtrace.agent",
    "roles/monitoring.metricWriter",
  ]
}

# The cluster creates the identity pool these principals live in, so every grant waits for it.
resource "google_project_iam_member" "runtime" {
  for_each   = { for p in setproduct(local.runtime_ksas, local.runtime_roles) : "${p[0]}-${p[1]}" => p }
  project    = var.project_id
  role       = each.value[1]
  member     = local.ksa[each.value[0]]
  depends_on = [google_container_cluster.gke]
}

# Vertex AI access only when the provider is vertex (otherwise an API key is used).
resource "google_project_iam_member" "vertex" {
  for_each   = var.llm_provider == "vertex" ? toset(["reader", "agent"]) : toset([])
  project    = var.project_id
  role       = "roles/aiplatform.user"
  member     = local.ksa[each.key]
  depends_on = [google_container_cluster.gke]
}

resource "google_storage_bucket_iam_member" "docs" {
  for_each   = toset(local.runtime_ksas)
  bucket     = google_storage_bucket.documents.name
  role       = each.key == "api" ? "roles/storage.objectAdmin" : "roles/storage.objectViewer"
  member     = local.ksa[each.key]
  depends_on = [google_container_cluster.gke]
}

resource "google_secret_manager_secret_iam_member" "secrets" {
  for_each = { for p in setproduct(local.runtime_ksas, ["db", "gemini", "langsmith"]) : "${p[0]}-${p[1]}" => p }
  secret_id = {
    db        = google_secret_manager_secret.db_password.id
    gemini    = google_secret_manager_secret.gemini_key.id
    langsmith = google_secret_manager_secret.langsmith_key.id
  }[each.value[1]]
  role       = "roles/secretmanager.secretAccessor"
  member     = local.ksa[each.value[0]]
  depends_on = [google_container_cluster.gke]
}

# ---------------------------------------------------------------- GitHub Actions (no JSON keys)
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  # Only this repository's main branch may deploy.
  attribute_condition = "assertion.repository == \"${var.github_repository}\" && assertion.ref == \"refs/heads/main\""
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_impersonates_deployer" {
  service_account_id = google_service_account.sa["deployer"].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

# Push images and apply manifests in the cluster (container.developer cannot change RBAC).
resource "google_project_iam_member" "deployer" {
  for_each = toset(["roles/container.developer", "roles/artifactregistry.writer"])
  project  = var.project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.sa["deployer"].email}"
}
