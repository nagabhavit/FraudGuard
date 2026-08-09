# =============================================================================
# ElastiCache Redis -- plan/validate only. Milestone 23.
#
# Nothing here has ever been applied: no real ElastiCache cluster exists
# because of this file. Checked with `terraform init -backend=false &&
# terraform validate` -- never `plan` or `apply`, and no AWS credentials
# are used or required anywhere in this milestone.
#
# ElastiCache is the preferred production architecture for FraudGuard's
# Redis (approved decision, this milestone), over self-hosting Redis as
# a StatefulSet in EKS. engine_version 7.1 matches docker-compose.yml's
# `redis:7-alpine` major version -- the highest Redis OSS version
# ElastiCache currently supports for the 7.x line (7.2+ is Valkey-only),
# re-verified against AWS's own documentation immediately before
# implementation, not invented.
#
# A single-node aws_elasticache_replication_group (num_cache_clusters=1,
# automatic_failover_enabled=false) is the smallest correct match for
# docker-compose.yml's own single Redis container -- no read replicas,
# no cluster-mode, no automatic failover. A replication group, not the
# plainer aws_elasticache_cluster resource, is used specifically because
# at-rest encryption for Redis is only exposed through the replication-
# group API in AWS -- confirmed by `terraform validate` itself rejecting
# at_rest_encryption_enabled on aws_elasticache_cluster as an unsupported
# argument; this is a real AWS API constraint, not a Terraform choice.
# Node type is an illustrative starting value, not capacity planning --
# per this project's "no invented numbers presented as fact" discipline
# (ADR-0015). Real Multi-AZ/multi-node hardening is out of scope here
# and named as future work, not an oversight, consistent with Milestone
# 18's already-documented cost-optimized, non-HA posture.
# =============================================================================

resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.cluster_name}-redis"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id       = "${var.cluster_name}-redis"
  description                = "FraudGuard Redis (feature store / cache)"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = "cache.t3.micro"
  num_cache_clusters         = 1
  automatic_failover_enabled = false
  port                       = 6379

  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [aws_security_group.elasticache.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  tags = {
    Environment = var.environment
  }
}
