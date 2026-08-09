# =============================================================================
# RDS PostgreSQL -- plan/validate only. Milestone 23.
#
# Nothing here has ever been applied: no real RDS instance exists
# because of this file. Checked with `terraform init -backend=false &&
# terraform validate` -- never `plan` or `apply`, and no AWS credentials
# are used or required anywhere in this milestone.
#
# RDS is the preferred production architecture for FraudGuard's Postgres
# (approved decision, this milestone), over self-hosting Postgres as a
# StatefulSet in EKS. engine_version 16.14 matches docker-compose.yml's
# `postgres:16-alpine` major version -- the current RDS-supported minor
# for major version 16, re-verified against AWS's own release notes
# immediately before implementation, not invented.
#
# manage_master_user_password = true: RDS's own native master-password-
# in-Secrets-Manager feature. No password variable, no plaintext
# credential anywhere in this file or state -- distinct from, and not a
# substitute for, Milestone 29's application-level Secrets Manager/
# External Secrets Operator wiring (that connects the application to
# this database's credentials; this is RDS managing its own master
# credential).
#
# Instance class, storage size, and multi_az are illustrative starting
# values, not capacity planning -- per this project's "no invented
# numbers presented as fact" discipline (ADR-0015). multi_az = false
# matches Milestone 18's already-documented cost-optimized, non-HA
# posture (single NAT gateway) rather than silently contradicting it
# with a multi-AZ database; real Multi-AZ failover is out of scope here
# and named as future work, not an oversight.
# =============================================================================

resource "aws_db_subnet_group" "this" {
  name       = "${var.cluster_name}-rds"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name        = "${var.cluster_name}-rds-subnet-group"
    Environment = var.environment
  }
}

resource "aws_db_instance" "this" {
  identifier     = "${var.cluster_name}-postgres"
  engine         = "postgres"
  engine_version = "16.14"

  instance_class    = "db.t3.micro"
  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "fraudguard"
  username = "fraudguard"

  # RDS-managed master credential -- see header. No password argument.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  multi_az               = false

  backup_retention_period   = 7
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.cluster_name}-postgres-final"

  tags = {
    Environment = var.environment
  }
}
