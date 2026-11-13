# Cloud SQL for PostgreSQL and Memorystore for Redis - both private, both always on
# (they bill while idle; see the cost warning in the README).

resource "google_sql_database_instance" "pg" {
  name                = "${local.name}-pg"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = true

  settings {
    tier              = var.sql_tier
    edition           = "ENTERPRISE"
    availability_type = "ZONAL"
    disk_size         = 20
    disk_type         = "PD_SSD"
    user_labels       = local.labels

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "20:30" # 02:00 IST
    }
    insights_config {
      query_insights_enabled = true # slow-query monitoring
    }
    database_flags {
      name  = "max_connections"
      value = "200"
    }
  }
  depends_on = [google_service_networking_connection.psa]
}

resource "google_sql_database" "app" {
  name     = "crossexam"
  instance = google_sql_database_instance.pg.name
}

resource "google_sql_user" "app" {
  name     = "crossexam"
  instance = google_sql_database_instance.pg.name
  password = random_password.db.result
}

# The `vector` extension (pgvector) is created by the migrate job:
#   CREATE EXTENSION IF NOT EXISTS vector;   (Cloud SQL supports it without flags)
#
# Production hardening, not automated here: create a SELECT-only role for the agents'
# read tools (GRANT SELECT ON ALL TABLES ...) and point those tools at it.

resource "google_redis_instance" "cache" {
  name               = "${local.name}-redis"
  tier               = "BASIC"
  memory_size_gb     = 1
  region             = var.region
  redis_version      = "REDIS_7_2"
  authorized_network = google_compute_network.vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  labels             = local.labels
  depends_on         = [google_service_networking_connection.psa]
}
