# ADR-0017: EKS node group scaffolding

- **Status:** Accepted
- **Date:** 2026-08-09

## Context

Milestone 16 (ADR-0016) produced a plan/validate-only EKS cluster
*definition* -- a VPC, two public subnets, an IAM role for the control
plane, and the `aws_eks_cluster` resource itself. It deliberately stopped
there: "No node groups, no cluster add-ons ... no OIDC provider for IRSA
-- those are real, later decisions, not needed for a syntactically and
referentially valid cluster *definition*."

An EKS cluster with no worker nodes can never run a pod, regardless of
how correct `infra/k8s/`'s Deployment manifests are. Milestone 17 is the
next slice: the minimum AWS-mandated infrastructure for a managed node
group, still entirely plan/validate-only -- no AWS credentials, no
`terraform apply`, no real node ever launched. Per the same evidence-only
scoping this project has used since Milestone 12, Milestone 17 has no
textual anchor anywhere in the repository the way Milestones 29 and 31
do; it is scoped here as "the next infrastructure slice after Milestone
16," explicitly approved as such, not derived from a hint that doesn't
exist.

Four things needed deciding before any file was worth writing: where the
node group's subnets come from, how big to make it, which cluster
add-ons (if any) come with it, and where the new resources live in
`infra/terraform/`.

## Decision

**The node group reuses Milestone 16's existing public subnets --
`aws_subnet.public[*].id` -- rather than introducing new private subnets
and a NAT gateway.** This is the smallest correct slice and the
maximum-reuse option, but it is explicitly *not* how a real production
EKS cluster places worker nodes (they normally sit in private subnets,
with only load balancers in public ones). Documented as an accepted
simplification, the same way every prior ADR in this project has named a
gap rather than silently absorbed it -- not fixed here; private
networking is a later, explicitly-scoped decision if this project ever
gets there.

**Sizing is illustrative, not authoritative:** `desired_size = 1,
min_size = 1, max_size = 1`, one `instance_types` entry
(`t3.medium`). Per ADR-0015's "no invented numbers presented as fact"
discipline, these are stated as defaults an operator can override, not a
claim about real capacity planning -- nothing here is ever applied
against a real account regardless.

**No cluster add-ons, no OIDC/IRSA, in this milestone.** VPC CNI,
CoreDNS, and kube-proxy (`aws_eks_addon` resources) and an OIDC provider
for IAM Roles for Service Accounts remain exactly as deferred as
ADR-0016 already left them. A node group with no add-ons and no running
pods is still a syntactically and referentially valid Terraform
resource -- proving *that* is this milestone's whole scope, not standing
up working pod networking.

**New resources live in a new file, `infra/terraform/node_group.tf` --
`main.tf` is not modified at all.** `node_group.tf` only *references*
`aws_eks_cluster.this` and `aws_subnet.public[*].id`, both already
defined in `main.tf`; not one line of the existing cluster definition
changes. This is the cleanest possible demonstration of "reuse existing
resources," and keeps `main.tf`'s own docstring ("EKS cluster skeleton")
accurate rather than needing a rewrite to also describe node groups.

**Five new resources, each an AWS-documented requirement for any
functioning managed node group, not a design preference:**

- `aws_iam_role.eks_node_group` -- EKS mandates a separate IAM role for
  worker nodes (assumed by `ec2.amazonaws.com`), distinct from
  `aws_iam_role.eks_cluster` (assumed by `eks.amazonaws.com`,
  control-plane only). A managed node group cannot be created without
  it.
- `aws_iam_role_policy_attachment.eks_node_worker_policy`
  (`AmazonEKSWorkerNodePolicy`) -- lets a node register with and connect
  to the cluster.
- `aws_iam_role_policy_attachment.eks_node_cni_policy`
  (`AmazonEKS_CNI_Policy`) -- lets the VPC CNI plugin running on each
  node attach/configure ENIs so pods can get real VPC IP addresses.
- `aws_iam_role_policy_attachment.eks_node_ecr_policy`
  (`AmazonEC2ContainerRegistryReadOnly`) -- lets nodes pull container
  images. Declared now even though no registry is wired up yet
  (Milestone 31 territory) -- the same "free to declare, costs nothing,
  documents intent" reasoning ADR-0016 already used for the subnet's
  `kubernetes.io/role/elb` tag.
- `aws_eks_node_group.this` -- the node group itself, tying together the
  existing cluster, the new IAM role, and the existing public subnets;
  `depends_on` the three policy attachments above, mirroring exactly how
  `main.tf`'s `aws_eks_cluster.this` already depends on its own
  cluster-role policy attachment.

## Alternatives considered

- **New private subnets + a NAT gateway for the node group**, the
  production-realistic pattern. Rejected for this milestone: a NAT
  gateway, an Elastic IP, two more subnets, and a private route table is
  a materially bigger slice than "the minimum necessary node-group
  infrastructure" asked for, and nothing here is ever applied regardless
  -- the security concern a NAT gateway would address doesn't exist yet
  for a configuration that's never provisioned. Revisit if this project
  ever moves toward real provisioning.
- **A Terraform Registry community module for the node group** (e.g.
  `terraform-aws-modules/eks/aws//modules/eks-managed-node-group`).
  Rejected for the same reason ADR-0016 rejected one for the cluster
  itself: an external dependency this project doesn't otherwise have,
  and hand-written resources stay legible for a portfolio project's own
  review.
- **Installing VPC CNI/CoreDNS/kube-proxy as explicit `aws_eks_addon`
  resources now that a node group exists to run them on.** Rejected:
  still real, later decisions (versioning, update strategy, IRSA for the
  CNI's own IAM needs) that don't need to be made to prove a node
  group's own definition is valid, and pulling them in now would exceed
  "the minimum necessary node-group infrastructure" this milestone was
  scoped to.
- **A larger, more "production-shaped" node group** (multiple instance
  types, spot capacity, 2-3 desired nodes for HA). Rejected: no capacity
  planning has ever been done for this project, and inventing numbers to
  look more realistic is exactly what ADR-0015 already rejected doing
  for load-test defaults. `desired_size = 1` is honest about being a
  skeleton, not a claim about production sizing.

## Acceptance criteria

No AWS account, credentials, or real resource of any kind is required or
created by satisfying these criteria.

1. `terraform -chdir=infra/terraform init -backend=false` exits 0.
2. `terraform -chdir=infra/terraform validate` exits 0, with no AWS
   credentials present anywhere in the environment.
3. `aws_vpc`, `aws_subnet`, and `aws_eks_cluster` each still appear
   exactly once across all of `infra/terraform/*.tf` -- proving
   `node_group.tf` reuses Milestone 16's resources rather than
   duplicating them.
4. `main.tf` is byte-for-byte unchanged from Milestone 16.
5. Neither `terraform plan` nor `terraform apply` is run as part of
   "done."

## Consequences

**Positive**

- An EKS cluster definition that could, if ever actually applied, launch
  a real worker node -- the missing piece Milestone 16's own ADR named
  explicitly as deferred.
- Zero changes to any existing file (`main.tf` untouched); the entire
  addition is new, reviewable in isolation.
- Every new resource maps to a specific, named AWS requirement, not a
  guess -- nothing here could be trimmed further and still describe a
  valid node group.

**Negative, and accepted**

- Worker nodes in public subnets is a documented simplification, not a
  production-realistic pattern. Named here, not hidden; a private
  networking pass is explicitly future work.
- No pod networking add-ons means a real cluster built from this
  configuration would have a node with nothing productive running on
  it yet -- accepted, since proving the node group's own definition is
  valid is this milestone's entire scope.
- `desired_size = 1` has no redundancy and no real capacity behind it --
  accepted as an honest placeholder, not a claim.
