# =============================================================================
# EKS cluster skeleton -- plan/validate only. See ADR-0016.
#
# Nothing here has ever been applied: no real VPC, IAM role, or EKS
# cluster exists because of this file. It exists to prove the shape of
# the intended compute target (Amazon EKS, chosen explicitly in ADR-0016)
# is structurally valid Terraform, checked with `terraform init
# -backend=false && terraform validate` -- never `plan` or `apply`, and
# no AWS credentials are used or required anywhere in this milestone.
#
# Deliberately minimal: a VPC with two public subnets (the minimum EKS
# itself requires -- at least two subnets in two Availability Zones) and
# the IAM role + policy attachment the control plane needs. No node
# groups, no cluster add-ons (VPC CNI, CoreDNS, kube-proxy), no OIDC
# provider for IRSA -- those are real, later decisions, not needed for a
# syntactically and referentially valid cluster *definition*.
#
# Hand-written against the native hashicorp/aws provider, not a Terraform
# Registry community module (ADR-0016) -- no new third-party dependency,
# and nothing hidden inside a module's internals.
# =============================================================================

provider "aws" {
  region = var.aws_region
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "this" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name        = "${var.cluster_name}-vpc"
    Environment = var.environment
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.cluster_name}-igw"
  }
}

resource "aws_subnet" "public" {
  count = 2

  vpc_id                  = aws_vpc.this.id
  cidr_block              = "10.0.${count.index}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.cluster_name}-public-${count.index}"
    # Lets the AWS Load Balancer Controller discover these subnets
    # automatically -- a later-milestone concern (no controller is
    # installed by this milestone), tagged now since it costs nothing and
    # documents intent rather than being silently missing later.
    "kubernetes.io/role/elb" = "1"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = {
    Name = "${var.cluster_name}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_iam_role" "eks_cluster" {
  name = "${var.cluster_name}-eks-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_eks_cluster" "this" {
  name     = var.cluster_name
  role_arn = aws_iam_role.eks_cluster.arn
  # Pinned explicitly (Milestone 19) so cluster add-on versions
  # (infra/terraform/addons.tf) have a fixed Kubernetes minor version to
  # be verified compatible against, rather than floating with whatever
  # EKS treats as "current default" at apply time. Re-verify against
  # AWS's supported-version list before ever applying this for real --
  # standard support is time-bound per Kubernetes minor version.
  version = "1.35"

  vpc_config {
    subnet_ids = aws_subnet.public[*].id
  }

  tags = {
    Environment = var.environment
  }

  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]
}
