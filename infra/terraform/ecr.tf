# =============================================================================
# ECR repositories -- plan/validate only. Milestone 31.
#
# Nothing here has ever been applied: no real ECR repository exists
# because of this file. Checked with `terraform init -backend=false &&
# terraform validate` -- never `plan` or `apply`, and no AWS credentials
# are used or required anywhere in this milestone.
#
# One repository per image this project actually builds -- the four
# Python services' Dockerfiles (services/*/Dockerfile) plus the
# dashboard's (dashboard/Dockerfile), matching docker-compose.yml's own
# five `build:` blocks exactly. Every app-service Kubernetes manifest has
# named this exact gap since Milestone 16 ("Publishing this to a real
# registry (e.g. ECR) is deployment-pipeline work, Milestone 31").
#
# image_tag_mutability = "IMMUTABLE": matches the approved M31 decision
# to tag images with the Git commit SHA, never "latest" -- an immutable
# tag can't be silently overwritten to point at different image content
# after the fact, which is the whole point of using a SHA tag in the
# first place. scan_on_push and encryption are the same "cheap,
# unconditionally correct" additions this project has made for every
# other datastore since Milestone 23 (RDS's storage_encrypted, MSK's
# encryption_in_transit) -- not invented specifically for ECR.
# =============================================================================

locals {
  ecr_repository_names = [
    "gateway",
    "feature-service",
    "aggregator",
    "model-service",
    "dashboard",
  ]
}

resource "aws_ecr_repository" "this" {
  for_each = toset(local.ecr_repository_names)

  name                 = "${var.cluster_name}-${each.value}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Environment = var.environment
  }
}
