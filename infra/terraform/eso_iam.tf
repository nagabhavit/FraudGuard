# =============================================================================
# IRSA role for the External Secrets Operator -- plan/validate only.
# Milestone 29.
#
# Nothing here has ever been applied: no real IAM role or policy exists
# because of this file. Checked with `terraform init -backend=false &&
# terraform validate` -- never `plan` or `apply`, and no AWS credentials
# are used or required anywhere in this milestone.
#
# References only existing resources -- Milestone 20's OIDC provider
# (irsa.tf) -- no changes to main.tf, node_group.tf, addons.tf,
# networking.tf, or irsa.tf itself.
#
# The trust policy's Condition is scoped to exactly
# system:serviceaccount:external-secrets:external-secrets for both sub
# and aud -- not a blanket federation, same least-privilege pattern as
# Milestone 21's Load Balancer Controller role. "external-secrets" (the
# ServiceAccount name) is pinned explicitly at Helm-render time
# (infra/k8s/eso.yaml) specifically so this trust policy's reference to
# it is accurate -- confirmed against the real chart during
# implementation: with serviceAccount.create=false and no explicit
# serviceAccount.name, the controller Deployment falls back to the
# literal "default" ServiceAccount, which would have made this scoping
# silently wrong.
#
# Least-privilege IAM policy: read-only (GetSecretValue, DescribeSecret)
# on exactly two secrets -- the Grafana admin password
# (secrets_manager.tf, this milestone) and Milestone 23's existing
# RDS-native master-user secret (aws_db_instance.this.master_user_secret
# -- a real Terraform reference, not a placeholder, since this is
# genuine HCL, not a static YAML file). Nothing broader.
# =============================================================================

resource "aws_iam_policy" "eso" {
  name = "${var.cluster_name}-eso-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret",
      ]
      Resource = [
        aws_secretsmanager_secret.grafana_admin.arn,
        aws_db_instance.this.master_user_secret[0].secret_arn,
      ]
    }]
  })
}

resource "aws_iam_role" "eso" {
  name = "${var.cluster_name}-eso-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.this.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${replace(aws_iam_openid_connect_provider.this.url, "https://", "")}:aud" = "sts.amazonaws.com"
          "${replace(aws_iam_openid_connect_provider.this.url, "https://", "")}:sub" = "system:serviceaccount:external-secrets:external-secrets"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eso" {
  role       = aws_iam_role.eso.name
  policy_arn = aws_iam_policy.eso.arn
}
