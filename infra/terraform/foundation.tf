# APIs, network, storage, registry and secrets.

resource "google_project_service" "apis" {
  for_each = toset([
    "container.googleapis.com", "sqladmin.googleapis.com", "redis.googleapis.com", "compute.googleapis.com",
    "servicenetworking.googleapis.com", "secretmanager.googleapis.com", "artifactregistry.googleapis.com",
    "monitoring.googleapis.com", "logging.googleapis.com", "cloudtrace.googleapis.com",
    "iamcredentials.googleapis.com", "sts.googleapis.com", "aiplatform.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------- network
resource "google_compute_network" "vpc" {
  name                    = "${local.name}-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}

resource "google_compute_subnetwork" "gke" {
  name                     = "${local.name}-gke"
  network                  = google_compute_network.vpc.id
  region                   = var.region
  ip_cidr_range            = "10.10.0.0/20" # nodes
  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.20.0.0/16"
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.30.0.0/20"
  }
}

# Nodes have no public IPs; Cloud NAT gives them outbound internet (Gemini API, LangSmith,
# the KEDA images on ghcr.io).
resource "google_compute_router" "nat" {
  name    = "${local.name}-router"
  network = google_compute_network.vpc.id
  region  = var.region
}

resource "google_compute_router_nat" "nat" {
  name                               = "${local.name}-nat"
  router                             = google_compute_router.nat.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# Private Service Access: Cloud SQL and Memorystore get private IPs inside the VPC, which pods
# reach directly. Allocated after the subnet so the range cannot overlap the pod range.
resource "google_compute_global_address" "psa" {
  name          = "${local.name}-psa"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.vpc.id
  depends_on    = [google_compute_subnetwork.gke]
}

resource "google_service_networking_connection" "psa" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.psa.name]
}

# ---------------------------------------------------------------- storage
resource "google_storage_bucket" "documents" {
  name                        = "${var.project_id}-${local.name}-documents"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = local.labels

  lifecycle_rule {
    condition { age = 90 }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
}

resource "google_artifact_registry_repository" "repo" {
  repository_id = local.name
  location      = var.region
  format        = "DOCKER"
  labels        = local.labels
  depends_on    = [google_project_service.apis]
}

# ---------------------------------------------------------------- secrets
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "${local.name}-db-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db.result
}

# Values for these two are added by you, never by Terraform (keeps keys out of state):
#   gcloud secrets versions add crossexam-gemini-api-key --data-file=key.txt
resource "google_secret_manager_secret" "gemini_key" {
  secret_id = "${local.name}-gemini-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "langsmith_key" {
  secret_id = "${local.name}-langsmith-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

# Pods mount every secret listed in infra/k8s/base/secrets.yaml, and a mount fails when a
# secret has no version. A key this configuration does not use gets the value "unused",
# which the container entrypoint skips.
resource "google_secret_manager_secret_version" "unused" {
  for_each = merge(
    var.llm_provider == "gemini" ? {} : { gemini = google_secret_manager_secret.gemini_key.id },
    var.langsmith_enabled ? {} : { langsmith = google_secret_manager_secret.langsmith_key.id },
  )
  secret      = each.value
  secret_data = "unused"
}
