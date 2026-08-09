# =============================================================================
# EKS managed node group -- plan/validate only. See ADR-0017.
#
# Nothing here has ever been applied: no real IAM role or node group
# exists because of this file. It exists to prove the shape of the
# minimum AWS-mandated infrastructure a managed node group needs is
# structurally valid Terraform, checked with `terraform init
# -backend=false && terraform validate` -- never `plan` or `apply`, and
# no AWS credentials are used or required anywhere in this milestone.
#
# main.tf is not modified by this file -- every resource below only
# references main.tf's existing aws_eks_cluster.this and
# aws_subnet.public[*].id, reusing Milestone 16's cluster and subnets
# rather than duplicating them (ADR-0017).
#
# Deliberately minimal: the node group itself and the three IAM policy
# attachments AWS requires for any managed node group to function. No
# cluster add-ons (VPC CNI, CoreDNS, kube-proxy), no OIDC provider for
# IRSA, no private subnets/NAT gateway -- all real, later decisions
# (ADR-0017's Alternatives considered).
# =============================================================================

resource "aws_iam_role" "eks_node_group" {
  name = "${var.cluster_name}-eks-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# The three AWS-documented minimum policies for any functioning managed
# node group -- not a design preference, a hard requirement.

resource "aws_iam_role_policy_attachment" "eks_node_worker_policy" {
  role       = aws_iam_role.eks_node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "eks_node_cni_policy" {
  role       = aws_iam_role.eks_node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "eks_node_ecr_policy" {
  role       = aws_iam_role.eks_node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_eks_node_group" "this" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "${var.cluster_name}-nodes"
  node_role_arn   = aws_iam_role.eks_node_group.arn
  # Reuses main.tf's existing public subnets (ADR-0017) rather than
  # introducing private subnets + a NAT gateway -- the smallest correct
  # slice, documented here as a simplification, not a production-realistic
  # pattern (real EKS worker nodes normally sit in private subnets).
  subnet_ids = aws_subnet.public[*].id

  instance_types = [var.node_instance_type]

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  tags = {
    Environment = var.environment
  }

  # AWS requires these policies attached before a node group creation
  # attempt succeeds -- the same ordering main.tf's aws_eks_cluster.this
  # already documents for its own cluster-role policy attachment.
  depends_on = [
    aws_iam_role_policy_attachment.eks_node_worker_policy,
    aws_iam_role_policy_attachment.eks_node_cni_policy,
    aws_iam_role_policy_attachment.eks_node_ecr_policy,
  ]
}
