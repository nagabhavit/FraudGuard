# =============================================================================
# GitHub Actions OIDC provider + IAM roles -- plan/validate only.
# Milestone 31.
#
# Nothing here has ever been applied: no real OIDC provider, IAM role, or
# EKS access entry exists because of this file. Checked with `terraform
# init -backend=false && terraform validate` -- never `plan` or `apply`,
# and no AWS credentials are used or required anywhere in this milestone.
#
# APPROVED DECISION: OIDC federation, not long-lived AWS access keys.
# Follows the exact IRSA pattern already established for every other AWS
# identity in this project (Milestone 20's EKS OIDC provider, Milestone
# 21's Load Balancer Controller role, Milestone 29's ESO role) --
# GitHub Actions authenticates as a federated identity, assumes a
# narrowly-scoped role for the duration of one job, and no standing
# credential is ever stored as a GitHub secret. This is a SEPARATE OIDC
# provider from irsa.tf's -- that one federates Kubernetes ServiceAccount
# tokens (issued by the EKS cluster's own OIDC issuer); this one
# federates GitHub Actions workflow tokens (issued by
# token.actions.githubusercontent.com) -- different issuer, different
# trust boundary, correctly modeled as two distinct provider resources.
#
# thumbprint_list intentionally omitted -- same investigated, documented
# reasoning as irsa.tf (Milestone 20): optional since provider v5.81.0
# (this project is locked to 5.100.0), and AWS IAM validates via the
# trusted root CA rather than a stored thumbprint as of AWS's July 2024
# change, which applies to any OIDC provider using a trusted CA, not
# just EKS's.
#
# TWO roles, not one, per this project's established "narrowly-scoped
# role per concern" discipline (never one blanket role for multiple
# jobs with different real permissions):
#
# - lb_controller/eso role precedent: aws_iam_role.github_actions_ecr_push
#   is scoped to system:... no -- GitHub's own equivalent: the OIDC
#   `sub` claim restricted to `repo:nagabhavit/FraudGuard:ref:refs/heads/
#   main` (only workflow runs actually triggered on main can assume it),
#   permissioned for ECR push only -- it has no EKS access at all.
# - aws_iam_role.github_actions_deploy is scoped to `sub` =
#   `repo:nagabhavit/FraudGuard:environment:production` -- only a job
#   using the (not-yet-created, see .github/workflows/deploy.yml's own
#   comments) "production" GitHub Environment can assume it. Permissioned
#   for eks:DescribeCluster only, plus an EKS access entry granting it
#   cluster edit access via Kubernetes RBAC -- it has no ECR push access
#   at all.
# =============================================================================

resource "aws_iam_openid_connect_provider" "github_actions" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# ---------------------------------------------------------------------------
# Role 1: build-and-push job -- ECR push only, no EKS access.
# ---------------------------------------------------------------------------

resource "aws_iam_role" "github_actions_ecr_push" {
  name = "${var.cluster_name}-github-actions-ecr-push"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github_actions.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:nagabhavit/FraudGuard:ref:refs/heads/main"
        }
      }
    }]
  })
}

resource "aws_iam_policy" "github_actions_ecr_push" {
  name = "${var.cluster_name}-github-actions-ecr-push-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # GetAuthorizationToken has no resource-level permissions in the
        # ECR API -- AWS documents this action as always requiring
        # Resource: "*"; it is not a broader grant chosen here.
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:BatchGetImage",
        ]
        Resource = [for repo in aws_ecr_repository.this : repo.arn]
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "github_actions_ecr_push" {
  role       = aws_iam_role.github_actions_ecr_push.name
  policy_arn = aws_iam_policy.github_actions_ecr_push.arn
}

# ---------------------------------------------------------------------------
# Role 2: production deploy job -- EKS access only, no ECR access.
# ---------------------------------------------------------------------------

resource "aws_iam_role" "github_actions_deploy" {
  name = "${var.cluster_name}-github-actions-deploy"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github_actions.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:nagabhavit/FraudGuard:environment:production"
        }
      }
    }]
  })
}

resource "aws_iam_policy" "github_actions_deploy" {
  name = "${var.cluster_name}-github-actions-deploy-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      # Only what `aws eks update-kubeconfig` needs to authenticate.
      # Authorization for what the role can then do inside the cluster
      # is governed by Kubernetes RBAC via the EKS access entry below,
      # not by this IAM policy.
      Effect   = "Allow"
      Action   = ["eks:DescribeCluster"]
      Resource = aws_eks_cluster.this.arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "github_actions_deploy" {
  role       = aws_iam_role.github_actions_deploy.name
  policy_arn = aws_iam_policy.github_actions_deploy.arn
}

# EKS access entry: the modern (non-aws-auth-ConfigMap) way to grant an
# IAM principal real Kubernetes RBAC permissions. AmazonEKSEditPolicy
# (not Admin) -- can create/update/delete workloads (what `kubectl set
# image` needs) but not manage RBAC or cluster-scoped resources itself.
resource "aws_eks_access_entry" "github_actions_deploy" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = aws_iam_role.github_actions_deploy.arn
}

resource "aws_eks_access_policy_association" "github_actions_deploy" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = aws_iam_role.github_actions_deploy.arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"

  access_scope {
    type = "cluster"
  }
}
