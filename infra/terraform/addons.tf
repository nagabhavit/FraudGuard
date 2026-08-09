# =============================================================================
# EKS managed add-ons -- plan/validate only. Milestone 19.
#
# Nothing here has ever been applied: no real add-on exists because of
# this file. Checked with `terraform init -backend=false && terraform
# validate` -- never `plan` or `apply`, and no AWS credentials are used
# or required anywhere in this milestone.
#
# The three AWS-documented core add-ons for a functioning managed node
# group's pod networking/DNS/service-proxy -- not a design preference,
# the minimum a real cluster would need to run any pod at all. Versions
# are pinned explicitly (not `most_recent = true`), matching this
# project's existing reproducibility discipline (uv.lock, pinned Alembic
# migrations, `~> 5.0` provider constraint) rather than silently
# floating to whatever AWS currently considers latest.
#
# Every version below was verified against AWS's official, current
# per-add-on version tables (docs.aws.amazon.com/eks/latest/userguide/
# managing-vpc-cni.html, managing-coredns.html, managing-kube-proxy.html)
# for Kubernetes 1.35 (main.tf's aws_eks_cluster.this.version), not
# invented. AWS updates these patch builds independently of the
# Kubernetes minor version on its own cadence -- re-verify against the
# same three pages before ever applying this for real, if meaningful
# time has passed since this file was written.
# =============================================================================

resource "aws_eks_addon" "vpc_cni" {
  cluster_name  = aws_eks_cluster.this.name
  addon_name    = "vpc-cni"
  addon_version = "v1.22.4-eksbuild.3"
}

resource "aws_eks_addon" "coredns" {
  cluster_name  = aws_eks_cluster.this.name
  addon_name    = "coredns"
  addon_version = "v1.14.3-eksbuild.3"
}

resource "aws_eks_addon" "kube_proxy" {
  cluster_name  = aws_eks_cluster.this.name
  addon_name    = "kube-proxy"
  addon_version = "v1.35.3-eksbuild.13"
}
