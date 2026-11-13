# GKE Autopilot cluster and the platform layer the manifests in infra/k8s rely on.
#
# Autopilot manages the nodes and bills for what pods request. Nodes are private; the
# control plane keeps a public endpoint (protected by IAM) so GitHub-hosted runners can deploy.

resource "google_container_cluster" "gke" {
  name                = "${local.name}-gke"
  location            = var.region
  enable_autopilot    = true
  deletion_protection = false # stateless: everything worth keeping is in Cloud SQL and Cloud Storage
  network             = google_compute_network.vpc.id
  subnetwork          = google_compute_subnetwork.gke.id
  resource_labels     = local.labels

  release_channel {
    channel = "REGULAR"
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
  }

  # Secret Manager secrets mounted as files (CSI driver secrets-store-gke.csi.k8s.io).
  secret_manager_config {
    enabled = true
  }

  cluster_autoscaling {
    auto_provisioning_defaults {
      service_account = google_service_account.sa["nodes"].email
      oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    }
  }

  depends_on = [google_project_service.apis, google_project_iam_member.nodes]
}

# ---------------------------------------------------------------- platform layer
resource "kubernetes_namespace_v1" "app" {
  metadata {
    name   = local.namespace
    labels = local.labels
  }
}

# Every infrastructure value a pod needs; the manifests load it with envFrom.
resource "kubernetes_config_map_v1" "app" {
  metadata {
    name      = "${local.name}-config"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }
  data = local.app_config
}

# KEDA scales the Celery workers on Redis queue length and on the month-end schedule
# (ScaledObjects in infra/k8s/app/workers.yaml).
resource "helm_release" "keda" {
  name             = "keda"
  repository       = "https://kedacore.github.io/charts"
  chart            = "keda"
  version          = var.keda_version
  namespace        = "keda"
  create_namespace = true

  # On private nodes the control plane may reach pods only on ports 443 and 10250, so KEDA's
  # metrics API (default 6443) and admission webhooks (default 9443) listen on 10250.
  set = [
    { name = "service.portHttpsTarget", value = "10250" },
    { name = "webhooks.port", value = "10250" },
  ]
}
