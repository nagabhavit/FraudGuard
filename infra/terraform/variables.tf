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

# The following four describe the EKS managed node group (ADR-0017).
# Illustrative defaults, not capacity planning -- nothing here is ever
# applied against a real account, so there is no real workload to size
# against yet.

variable "node_instance_type" {
  description = "EC2 instance type for the EKS managed node group. Never actually launched in Milestone 17 -- plan/validate only (ADR-0017)."
  type        = string
  default     = "t3.medium"
}

variable "node_desired_size" {
  description = "Desired worker node count. Not a capacity decision -- see ADR-0017."
  type        = number
  default     = 1
}

variable "node_min_size" {
  description = "Minimum worker node count. Not a capacity decision -- see ADR-0017."
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum worker node count. Not a capacity decision -- see ADR-0017."
  type        = number
  default     = 1
}
