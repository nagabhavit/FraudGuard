# See ADR-0016 -- neither output resolves to anything real until this
# configuration is actually applied, which this milestone deliberately
# never does.

output "cluster_name" {
  description = "EKS cluster name. Not a real cluster -- see ADR-0016."
  value       = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  description = "EKS API server endpoint. Would only resolve to something real once actually applied, which Milestone 16 deliberately never does."
  value       = aws_eks_cluster.this.endpoint
}

output "node_group_name" {
  description = "EKS managed node group name. Not a real node group -- see ADR-0017."
  value       = aws_eks_node_group.this.node_group_name
}

output "node_group_status" {
  description = "EKS managed node group status. Would only resolve to something real once actually applied, which Milestone 17 deliberately never does."
  value       = aws_eks_node_group.this.status
}
