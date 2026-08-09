# =============================================================================
# Security groups for the managed datastores -- plan/validate only.
# Milestone 23.
#
# Nothing here has ever been applied: no real security group exists
# because of this file. Checked with `terraform init -backend=false &&
# terraform validate` -- never `plan` or `apply`, and no AWS credentials
# are used or required anywhere in this milestone.
#
# Ingress is restricted to exactly one source: the EKS cluster's own
# auto-created cluster security group (aws_eks_cluster.this.vpc_config[0]
# .cluster_security_group_id) -- the same security group every node and
# pod in the cluster is a member of. No public ingress, ever. Both
# security groups live in the VPC only -- placement in the private
# subnets (Milestone 18) happens via each datastore's own subnet group,
# not via the security group itself.
# =============================================================================

resource "aws_security_group" "rds" {
  name_prefix = "${var.cluster_name}-rds-"
  vpc_id      = aws_vpc.this.id
  description = "Allow Postgres from the EKS cluster only"

  ingress {
    description     = "Postgres from EKS cluster nodes/pods"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_eks_cluster.this.vpc_config[0].cluster_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.cluster_name}-rds-sg"
    Environment = var.environment
  }
}

resource "aws_security_group" "elasticache" {
  name_prefix = "${var.cluster_name}-elasticache-"
  vpc_id      = aws_vpc.this.id
  description = "Allow Redis from the EKS cluster only"

  ingress {
    description     = "Redis from EKS cluster nodes/pods"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_eks_cluster.this.vpc_config[0].cluster_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.cluster_name}-elasticache-sg"
    Environment = var.environment
  }
}
