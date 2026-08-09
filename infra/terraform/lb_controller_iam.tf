# =============================================================================
# IRSA role for the AWS Load Balancer Controller -- plan/validate only.
# Milestone 21.
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
# system:serviceaccount:kube-system:aws-load-balancer-controller for both
# sub and aud -- not a blanket federation. Any pod that can present a
# token for that one specific ServiceAccount can assume this role;
# nothing else in the cluster can, per the least-privilege scoping
# already agreed for M20/M21.
#
# lb_controller_iam_policy.json is the real, official AWS Load Balancer
# Controller IAM policy, downloaded verbatim from the v3.5.0 release tag
# of kubernetes-sigs/aws-load-balancer-controller (docs/install/
# iam_policy.json) -- re-verified against the live upstream source
# immediately before this file was written, not reused from an earlier,
# now-outdated investigation (which had found v2.14.1; the real current
# release turned out to be v3.5.0, a major version). Not hand-authored
# or simplified in any way.
# =============================================================================

resource "aws_iam_policy" "lb_controller" {
  name   = "${var.cluster_name}-lb-controller-policy"
  policy = file("${path.module}/lb_controller_iam_policy.json")
}

resource "aws_iam_role" "lb_controller" {
  name = "${var.cluster_name}-lb-controller-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.this.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${replace(aws_iam_openid_connect_provider.this.url, "https://", "")}:aud" = "sts.amazonaws.com"
          "${replace(aws_iam_openid_connect_provider.this.url, "https://", "")}:sub" = "system:serviceaccount:kube-system:aws-load-balancer-controller"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lb_controller" {
  role       = aws_iam_role.lb_controller.name
  policy_arn = aws_iam_policy.lb_controller.arn
}
