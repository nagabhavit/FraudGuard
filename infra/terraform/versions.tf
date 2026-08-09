# Plan/validate only -- see ADR-0016. Nothing in infra/terraform/ has ever
# been applied; validated with `terraform init -backend=false && terraform
# validate`, never `plan` or `apply`, and no AWS credentials are used or
# required anywhere in this milestone.

terraform {
  required_version = ">= 1.7, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # The intended remote-state target -- .gitignore already reserves
  # .terraform/ and *.tfstate for it, with its own comment naming "an
  # encrypted S3 bucket with DynamoDB locking." Never initialized against
  # in this milestone: `terraform init -backend=false` skips backend
  # initialization entirely, which is what this milestone's validation
  # actually runs. bucket/key/region/dynamodb_table are intentionally
  # left unset -- a real backend config needs an already-provisioned
  # bucket and lock table, neither of which this milestone creates;
  # supplying them via `-backend-config` is future work alongside the
  # bucket/table's own Terraform, not hardcoded here.
  backend "s3" {}
}
