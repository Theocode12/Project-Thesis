# CloudFormation Deployments

These templates assume that the VPC and subnets already exist. The dashboard
subnet must provide a public IPv4 address and an internet route. Processing and
source subnets may be private, but they need NAT or another outbound path for
the initial `apt-get` and Git bootstrap.

## Templates

- `edge-only.yaml` creates one dashboard instance and one edge instance.
- `cloud-only.yaml` creates one dashboard instance, one cloud processing
  instance, and one industrial/source instance.
- `hybrid.yaml` creates the dashboard, edge, and cloud instances as one unit.

All templates install Docker, clone `RepositoryUrl`, and start the relevant
Compose file. The repository URL must be accessible from the instances during
bootstrap.

## Certificate Parameters

For the current test deployment, pass `CaddyCertificate` and
`CaddyPrivateKey` as `NoEcho` parameters. The dashboard user data writes them
to the cloned repository’s `certs/` directory before starting Caddy. This
matches the relative certificate mounts in the dashboard Compose files. Do
not expose either value in stack outputs or logs.

The hybrid template directly wires the edge and cloud private IP addresses and
security groups together, so there is no cross-stack dependency cycle.

## Important Parameters

- `AmiId` should be an Ubuntu 22.04 or 24.04 x86_64 image with cloud-init.
- `AdminCidr` controls temporary SSH access and defaults to `0.0.0.0/0` for
  testing. Restrict it before any sustained deployment.
- `RepositoryRef` selects the Git branch or tag used by the instances.
- Private MQTT and classifier addresses should be private IPs or private DNS
  names, not public endpoints.
