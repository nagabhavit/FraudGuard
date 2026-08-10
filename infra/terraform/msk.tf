# =============================================================================
# AWS MSK (Managed Streaming for Apache Kafka) -- plan/validate only.
# Milestone 24.
#
# Nothing here has ever been applied: no real MSK cluster exists because
# of this file. Checked with `terraform init -backend=false && terraform
# validate` -- never `plan` or `apply`, and no AWS credentials are used
# or required anywhere in this milestone.
#
# MSK is the preferred production architecture for FraudGuard's Kafka
# (approved decision, this milestone), over self-hosting Kafka as a
# StatefulSet in EKS -- consistent with ADR-0016's own speculation.
#
# TERRAFORM INFRASTRUCTURE ONLY: this file provisions the MSK cluster
# itself. Topic creation and configuration (bootstrap-broker-pointed,
# RF=3 applied per-topic) is deliberately NOT done here -- that is
# imperative, not Terraform, work, deferred to Milestone 29 alongside
# the rest of production Kafka configuration, the same way this project
# has never used Terraform for docker-compose's own local Kafka topic
# setup either.
#
# BROKER COUNT: 4, NOT 3 -- A REAL AWS CONSTRAINT, NOT A CHOICE:
# This project's Kafka topology has always been documented as "3
# brokers, RF=3" (docker-compose.yml's own comment,
# libs/fraudguard-events/src/fraudguard_events/topics.py). MSK requires
# number_of_broker_nodes to be an exact multiple of the number of
# subnets supplied in client_subnets -- confirmed against AWS's own MSK
# documentation before writing this file, not assumed. Milestone 18
# created exactly two private subnets (approved as unchanged for this
# milestone -- see the accepted two-AZ topology tradeoff below), and 3
# is not a multiple of 2: a literal 3-broker cluster across these two
# subnets is not a configuration AWS's API would ever accept, not merely
# a fault-isolation quality concern. 4 is the smallest multiple of 2
# that still satisfies RF=3's own minimum requirement (RF=3 needs at
# least 3 distinct broker nodes to place 3 replicas; 3 itself is
# unreachable here, so 4 is the correct smallest-correct-slice value,
# not an arbitrarily larger one).
#
# TWO-AZ TOPOLOGY, ACCEPTED TRADEOFF (approved decision, this
# milestone): brokers are distributed across Milestone 18's two private
# subnets, not three -- networking.tf is deliberately not reopened.
# With 4 brokers across 2 AZs (2 brokers per AZ), an AZ failure can take
# out up to half the cluster (2 of 4 brokers) at once, a materially
# weaker guarantee than a true 3-AZ/1-broker-per-AZ topology where an AZ
# failure costs at most one broker. This is a named, accepted tradeoff,
# not disguised as "multi-AZ HA" -- consistent with Milestone 18's own
# single-NAT-gateway, cost-optimized, non-HA posture.
#
# kafka_version "3.9.x" is AWS's own explicitly-labeled "(Recommended)"
# version as of this implementation (re-verified against AWS's live MSK
# supported-versions documentation immediately before writing this
# file, not reused from an earlier investigation) -- the last version to
# support both ZooKeeper and KRaft metadata management, with AWS's own
# extended-support commitment of at least two years from release.
# Instance type and storage size are illustrative starting values, not
# capacity planning -- per this project's "no invented numbers presented
# as fact" discipline (ADR-0015).
#
# encryption_in_transit.client_broker = "TLS" (no plaintext fallback)
# and encryption_at_rest_kms_key_arn left unset (defaults to an
# AWS-managed KMS key) -- encryption is a stated requirement for this
# project's datastore milestones (matching Milestone 23's
# storage_encrypted on RDS and at_rest_encryption_enabled on
# ElastiCache), not an MSK-specific addition invented here.
# =============================================================================

resource "aws_security_group" "msk" {
  name_prefix = "${var.cluster_name}-msk-"
  vpc_id      = aws_vpc.this.id
  description = "Allow Kafka (TLS) from the EKS cluster only"

  ingress {
    description     = "Kafka TLS broker traffic from EKS cluster nodes/pods"
    from_port       = 9094
    to_port         = 9094
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
    Name        = "${var.cluster_name}-msk-sg"
    Environment = var.environment
  }
}

resource "aws_msk_cluster" "this" {
  cluster_name           = "${var.cluster_name}-kafka"
  kafka_version          = "3.9.x"
  number_of_broker_nodes = 4

  broker_node_group_info {
    instance_type   = "kafka.t3.small"
    client_subnets  = aws_subnet.private[*].id
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info {
        volume_size = 100
      }
    }
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  tags = {
    Environment = var.environment
  }
}
