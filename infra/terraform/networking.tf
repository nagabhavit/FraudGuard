# =============================================================================
# Private networking for the EKS node group -- plan/validate only.
# Milestone 18.
#
# Nothing here has ever been applied: no real subnet, EIP, NAT gateway, or
# route table exists because of this file. Checked with `terraform init
# -backend=false && terraform validate` -- never `plan` or `apply`, and no
# AWS credentials are used or required anywhere in this milestone.
#
# Reuses the existing two-AZ topology main.tf already established in
# Milestone 16 (data.aws_availability_zones.available, aws_vpc.this) --
# no third AZ is introduced. main.tf's public subnets are left untouched
# and remain reserved for a future load balancer (Milestone 21); only
# node_group.tf is modified elsewhere, to point the EKS managed node
# group at the new private subnets below instead of the public ones.
#
# COST-OPTIMIZED, NOT MULTI-AZ HIGH AVAILABILITY:
# A single NAT gateway is used here to control cost for a portfolio
# deployment. Both private subnets route their default (0.0.0.0/0)
# egress through this one NAT gateway, which lives in a single AZ
# (aws_subnet.public[0]). This is not a multi-AZ HA pattern -- if that
# NAT gateway's AZ fails, private-subnet egress fails with it, for both
# AZs, since there is no per-AZ NAT gateway to fail over to. A
# production system with an uptime SLA would use one NAT gateway per AZ
# instead. This tradeoff is deliberate and approved (Milestone 18 scope),
# not an oversight.
# =============================================================================

resource "aws_subnet" "private" {
  count = 2

  vpc_id            = aws_vpc.this.id
  cidr_block        = "10.0.${count.index + 10}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "${var.cluster_name}-private-${count.index}"
  }
}

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name = "${var.cluster_name}-nat-eip"
  }
}

# Single NAT gateway, placed in the first public subnet -- see the
# cost-optimized, non-HA note above.
resource "aws_nat_gateway" "this" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = {
    Name = "${var.cluster_name}-nat"
  }

  # NAT gateway egress depends on the VPC already having internet access
  # via the Internet Gateway, the same ordering constraint AWS documents
  # for any NAT gateway.
  depends_on = [aws_internet_gateway.this]
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this.id
  }

  tags = {
    Name = "${var.cluster_name}-private-rt"
  }
}

resource "aws_route_table_association" "private" {
  count = length(aws_subnet.private)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
