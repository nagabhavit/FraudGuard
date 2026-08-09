# See ADR-0016. Every default here describes intent only -- nothing in
# this milestone applies these values against a real AWS account.

variable "aws_region" {
  description = "AWS region the EKS cluster skeleton targets. Never actually used to create anything in Milestone 16 -- plan/validate only (ADR-0016)."
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "EKS cluster name. Not yet created -- see ADR-0016."
  type        = string
  default     = "fraudguard"
}

variable "environment" {
  description = "Deployment environment tag. Only a conceptual \"dev\" exists until a real environment is provisioned, which is out of scope for this milestone (ADR-0016)."
  type        = string
  default     = "dev"
}
