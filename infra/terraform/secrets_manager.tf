# =============================================================================
# AWS Secrets Manager -- plan/validate only. Milestone 29.
#
# Nothing here has ever been applied: no real secret exists because of
# this file. Checked with `terraform init -backend=false && terraform
# validate` -- never `plan` or `apply`, and no AWS credentials are used
# or required anywhere in this milestone.
#
# ONE secret container defined here: the Grafana admin password.
# PostgreSQL's credential secret is NOT defined here -- Milestone 23's
# aws_db_instance.this already has manage_master_user_password = true,
# RDS's own native Secrets Manager integration. Defining a second,
# separate Postgres secret here would create a duplicate credential this
# project's own approved M29 scope explicitly rules out.
#
# No aws_secretsmanager_secret_version resource exists for the Grafana
# secret, deliberately -- this project does not invent or commit fake
# secret material, real or placeholder, to Terraform state. The actual
# admin password is populated out-of-band (AWS CLI/console) at real
# deployment time, by whoever owns that credential -- not by this
# milestone, which never applies anything regardless.
# =============================================================================

resource "aws_secretsmanager_secret" "grafana_admin" {
  name        = "${var.cluster_name}-grafana-admin"
  description = "Grafana admin password (Milestone 29) -- value populated out-of-band, never via Terraform."

  tags = {
    Environment = var.environment
  }
}
