# =============================================================================
# EKS OIDC provider for IRSA -- plan/validate only. Milestone 20.
#
# Nothing here has ever been applied: no real OIDC provider exists
# because of this file. Checked with `terraform init -backend=false &&
# terraform validate` -- never `plan` or `apply`, and no AWS credentials
# are used or required anywhere in this milestone.
#
# Provider only -- no IRSA-consuming IAM role, no IAM policy, and no
# Kubernetes ServiceAccount are created here. Those are each a specific,
# later milestone's own scope (the AWS Load Balancer Controller and
# External Secrets Operator), not this one's.
#
# thumbprint_list is intentionally omitted, not hardcoded. Investigated
# against this repository's locked hashicorp/aws provider (5.100.0,
# .terraform.lock.hcl) before writing this file: thumbprint_list became
# Optional in provider v5.81.0 (hashicorp/terraform-provider-aws#35112,
# #37255), so 5.100.0 already supports omitting it. As of AWS's July
# 2024 IAM change ("AWS Identity and Access Management simplifies
# management of OpenID Connect identity providers"), IAM validates an
# OIDC IdP's TLS certificate against its trusted root CA rather than a
# stored thumbprint -- which covers every AWS-region EKS OIDC issuer.
# When thumbprint_list is omitted, IAM auto-retrieves a thumbprint value
# for display/compatibility, but doesn't use it for validation. Hard-
# coding a thumbprint here would add a value AWS itself no longer
# actually relies on, and would reintroduce the exact fragility AWS's
# July 2024 change eliminated (a hardcoded Starfield-chain thumbprint is
# what broke industry-wide when that intermediate CA rotated in 2022).
# Omitting it also avoids adding the hashicorp/tls provider (the
# alternative, `data "tls_certificate"`-based pattern) -- no new
# provider dependency, consistent with ADR-0016/0017's "no new
# dependencies without asking."
# =============================================================================

resource "aws_iam_openid_connect_provider" "this" {
  url            = aws_eks_cluster.this.identity[0].oidc[0].issuer
  client_id_list = ["sts.amazonaws.com"]
}
