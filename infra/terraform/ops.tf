# Cloud Monitoring alerts. Month-end scaling and the housekeeping calls (reap-stale,
# nightly-check) run inside the cluster: KEDA and CronJobs in infra/k8s/app.

# ---------------------------------------------------------------- alerts
resource "google_monitoring_notification_channel" "email" {
  display_name = "crossexam alerts"
  type         = "email"
  labels       = { email_address = var.alert_email }
}

# An alert policy can only reference a metric Cloud Monitoring already knows, and the app
# registers each metric only when it first records a value (a task failure may never happen).
# So the alerted metrics are declared here exactly as the OpenTelemetry exporter creates them:
# same kind and value type, one label per attribute plus its opentelemetry_id. The exporter's
# own create call then just updates them; Terraform ignores that, since replacing a
# descriptor would delete its data.
locals {
  app_metrics = {
    crossexam_queue_length      = { kind = "GAUGE", type = "INT64", labels = ["queue"] }
    crossexam_task_failures     = { kind = "CUMULATIVE", type = "INT64", labels = ["task", "error"] }
    crossexam_llm_cost_usd      = { kind = "CUMULATIVE", type = "DOUBLE", labels = ["agent", "model"] }
    crossexam_injection_blocked = { kind = "CUMULATIVE", type = "INT64", labels = ["agent"] }
  }
}

resource "google_monitoring_metric_descriptor" "app" {
  for_each     = local.app_metrics
  type         = "workload.googleapis.com/${each.key}"
  display_name = each.key
  description  = "Written by the crossexam app (app/observability/metrics.py)"
  metric_kind  = each.value.kind
  value_type   = each.value.type

  dynamic "labels" {
    for_each = concat(each.value.labels, ["opentelemetry_id"])
    content {
      key = labels.value
    }
  }
  lifecycle {
    ignore_changes = all
  }
  depends_on = [google_project_service.apis]
}

locals {
  alerts = {
    urgent_queue_backlog = {
      name   = "Urgent queue backed up"
      filter = "metric.type=\"workload.googleapis.com/crossexam_queue_length\" AND metric.labels.queue=monitoring.regex.full_match(\".*urgent\")"
      value  = 50
      window = "1800s"
      align  = "ALIGN_MEAN"
      # Every API pod reports the same queue length: take the highest per queue, not the sum.
      reduce   = "REDUCE_MAX"
      group_by = ["metric.label.queue"]
    }
    task_failures = {
      name     = "Pipeline task failures"
      filter   = "metric.type=\"workload.googleapis.com/crossexam_task_failures\""
      value    = 10
      window   = "600s"
      align    = "ALIGN_DELTA"
      reduce   = "REDUCE_SUM" # counters: each worker pod counts its own work
      group_by = []
    }
    ai_spend = {
      name     = "Daily AI spend above budget"
      filter   = "metric.type=\"workload.googleapis.com/crossexam_llm_cost_usd\""
      value    = var.daily_ai_budget_usd
      window   = "86400s"
      align    = "ALIGN_DELTA"
      reduce   = "REDUCE_SUM"
      group_by = []
    }
    injection = {
      name     = "Prompt-injection attempts detected"
      filter   = "metric.type=\"workload.googleapis.com/crossexam_injection_blocked\""
      value    = 0
      window   = "3600s"
      align    = "ALIGN_DELTA"
      reduce   = "REDUCE_SUM"
      group_by = []
    }
  }
}

resource "google_monitoring_alert_policy" "custom" {
  for_each     = local.alerts
  display_name = each.value.name
  combiner     = "OR"
  conditions {
    display_name = each.value.name
    condition_threshold {
      filter          = "${each.value.filter} AND resource.type=\"generic_task\""
      comparison      = "COMPARISON_GT"
      threshold_value = each.value.value
      duration        = "0s"
      aggregations {
        alignment_period     = each.value.window
        per_series_aligner   = each.value.align
        cross_series_reducer = each.value.reduce
        group_by_fields      = each.value.group_by
      }
    }
  }
  notification_channels = [google_monitoring_notification_channel.email.id]
  documentation {
    content = "See the runbook in README.md, section 'When an alert fires'."
  }
  depends_on = [google_monitoring_metric_descriptor.app]
}

# The API has no load balancer in front of it, so its 5xx count comes from uvicorn's access
# log lines (`... "GET /stats HTTP/1.1" 500 Internal Server Error`) in Cloud Logging.
resource "google_logging_metric" "api_5xx" {
  name   = "${local.name}-api-5xx"
  filter = <<-EOT
    resource.type="k8s_container"
    resource.labels.namespace_name="${local.namespace}"
    resource.labels.container_name="api"
    textPayload=~"HTTP/[0-9.]+\" 5[0-9][0-9] "
  EOT
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "api_errors" {
  display_name = "API 5xx errors"
  combiner     = "OR"
  conditions {
    display_name = "5xx responses"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.api_5xx.name}\" AND resource.type=\"k8s_container\""
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      duration        = "0s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
  notification_channels = [google_monitoring_notification_channel.email.id]
}

resource "google_monitoring_alert_policy" "db_down" {
  display_name = "Cloud SQL unavailable"
  combiner     = "OR"
  conditions {
    display_name = "database is down"
    condition_threshold {
      filter          = "metric.type=\"cloudsql.googleapis.com/database/up\" AND resource.type=\"cloudsql_database\""
      comparison      = "COMPARISON_LT"
      threshold_value = 1
      duration        = "300s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }
  notification_channels = [google_monitoring_notification_channel.email.id]
}
