# Google Cloud deployment for the supply-chain document AI.
#
#   GKE Autopilot (private nodes, Cloud NAT) runs every component; the workloads themselves
#   are Kubernetes manifests in infra/k8s, rolled out by GitHub Actions
#   Cloud SQL PostgreSQL 16 (private IP, pgvector) | Memorystore Redis (private)
#   Cloud Storage | Secret Manager (GKE add-on) | Artifact Registry | KEDA (worker autoscaling)
#   Cloud Monitoring alerts | Workload Identity Federation for pods and for GitHub Actions
#
# Terraform owns the cloud resources and the cluster's platform layer (namespace, the config
# map built from the resources below, KEDA). It never touches images or Deployments.

terraform {
  required_version = ">= 1.6"
  required_providers {
    google     = { source = "hashicorp/google", version = ">= 6.40" }
    kubernetes = { source = "hashicorp/kubernetes", version = ">= 2.36" }
    helm       = { source = "hashicorp/helm", version = ">= 3.0" }
    random     = { source = "hashicorp/random", version = ">= 3.6" }
  }
  # State lives in a bucket you create once (see README):
  #   terraform init -backend-config="bucket=<your-state-bucket>"
  backend "gcs" {
    prefix = "crossexam"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "this" {}

data "google_client_config" "current" {}

# Both talk to the cluster created in gke.tf with your gcloud credentials.
provider "kubernetes" {
  host                   = "https://${google_container_cluster.gke.endpoint}"
  token                  = data.google_client_config.current.access_token
  cluster_ca_certificate = base64decode(google_container_cluster.gke.master_auth[0].cluster_ca_certificate)
}

provider "helm" {
  kubernetes = {
    host                   = "https://${google_container_cluster.gke.endpoint}"
    token                  = data.google_client_config.current.access_token
    cluster_ca_certificate = base64decode(google_container_cluster.gke.master_auth[0].cluster_ca_certificate)
  }
}

locals {
  name      = "crossexam"
  namespace = "crossexam" # must match infra/k8s
  labels    = { app = "crossexam", managed-by = "terraform" }

  # Settings shared by every container, published as the crossexam-config ConfigMap.
  # Secrets are not here: pods mount them from Secret Manager (infra/k8s/base/secrets.yaml).
  app_config = {
    ENV                     = "gcp"
    LLM_PROVIDER            = var.llm_provider
    GCP_PROJECT             = var.project_id
    GCP_LOCATION            = var.region
    STORAGE_BACKEND         = "gcs"
    GCS_BUCKET              = google_storage_bucket.documents.name
    DB_HOST                 = google_sql_database_instance.pg.private_ip_address
    DB_NAME                 = google_sql_database.app.name
    DB_USER                 = google_sql_user.app.name
    REDIS_URL               = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/0"
    REDIS_ADDRESS           = "${google_redis_instance.cache.host}:${google_redis_instance.cache.port}" # for KEDA
    METRICS_EXPORTER        = "gcp"
    OTEL_EXPORTER           = "gcp"
    LOG_LEVEL               = "INFO"
    LANGSMITH_TRACING       = var.langsmith_enabled ? "true" : "false"
    LANGSMITH_PROJECT       = "crossexam"
    LLM_REQUESTS_PER_MINUTE = tostring(var.llm_requests_per_minute)
  }
}
