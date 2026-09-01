# CloudFormation Deployments

Each template creates its own VPC, internet gateway, route table, and public
subnet. The subnet is derived from `VpcCidr`, and all instances receive public
IP addresses for the testing phase. The security groups still keep MQTT and
classifier ports restricted to the required instance-to-instance paths.

## Templates

- `edge-only.yaml` creates one dashboard instance and one edge instance.
- `cloud-only.yaml` creates one dashboard instance, one cloud processing
  instance, and one industrial/source instance.
- `hybrid.yaml` creates the dashboard, edge, and cloud instances as one unit.

All templates install Docker, clone `RepositoryUrl`, and start the relevant
Compose file. The repository URL must be accessible from the instances during
bootstrap. Bootstrap retries package and Git operations, validates the Compose
file, waits for required cross-instance ports, and writes logs to
`/var/log/thesis-bootstrap.log`.

## Certificate Parameters

The dashboard certificate and key are loaded automatically from SSM Parameter
Store parameters named `Certificate-Pem` and `Certificate-Key` in the stack's
AWS Region. Both parameters must contain the complete PEM blocks, including
their `BEGIN` and `END` lines. The templates write them to the cloned
repository's `certs/` directory and validate them before starting Caddy. The
CloudFormation deployment identity needs `ssm:GetParameter` permission for
both parameters. Do not expose either value in stack outputs or logs.

The hybrid template directly wires the edge and cloud private IP addresses and
security groups together, so there is no cross-stack dependency cycle.

## Important Parameters

- `AmiId` defaults to the regional Ubuntu 24.04 x86_64 public SSM parameter.
- `AdminCidr` controls temporary SSH access and defaults to `0.0.0.0/0` for
  testing. Restrict it before any sustained deployment.
- `RepositoryRef` selects the Git branch or tag used by the instances; it
  defaults to `research`.
- `RepositoryUrl` defaults to `https://github.com/Theocode12/Project-Thesis.git`.
- Default instance sizing uses `t3.micro` for dashboards and sources,
  `t3.small` for edge processing, and `m7i-flex.large` for cloud processing.
- Dashboard instances use an encrypted 10 GiB gp3 root volume. Processing
  instances use an encrypted 30 GB gp3 root volume because the detector and
  classifier images include CPU PyTorch dependencies.
- Processing image builds run sequentially to avoid concurrent Docker build
  layers exhausting the instance disk.
- The dashboard experiment recorder stores data under
  `/opt/project/app/experiments/{cloud_only|edge_only|hybrid}` and records
  anomaly, orchestration, classification, and service-status events as JSON
  Lines files. The directory is part of the cloned repository and can be
  reviewed or committed as experimental evidence.
- Sensor replay starts at the selected run and advances through the catalog in
  sequential order when a run ends; it no longer selects runs randomly.
- MQTT and classifier connections use private instance IPs even though the
  instances are in a public subnet.

## Validation

Before creating a stack, validate the template with the AWS CLI:

```bash
aws cloudformation validate-template \
  --template-body file://cloudformation/hybrid.yaml
```

Run the same command for `edge-only.yaml` and `cloud-only.yaml`. Validate each
Compose file from the repository root:

```bash
docker compose -f deployments/edge_only/edge-compose.yml config -q
docker compose -f deployments/edge_only/dashboard-compose.yml config -q
docker compose -f deployments/cloud_only/cloud-compose.yml config -q
docker compose -f deployments/cloud_only/dashboard-compose.yml config -q
docker compose -f deployments/cloud_only/source-compose.yml config -q
docker compose -f deployments/hybrid/edge-compose.yml config -q
docker compose -f deployments/hybrid/cloud-compose.yml config -q
docker compose -f deployments/hybrid/dashboard-compose.yml config -q

## Smoke Tests

After stack creation, confirm the dashboard URL from the stack output, then
check the instance bootstrap logs through SSM:

```bash
sudo tail -n 200 /var/log/thesis-bootstrap.log
docker compose -f deployments/<mode>/<file>.yml ps
```

For `edge-only`, verify dashboard-to-edge MQTT and the local classifier. For
`cloud-only`, verify dashboard/source-to-cloud MQTT and the cloud classifier.
For `hybrid`, verify both dashboard broker connections and the edge diagnosis
request to the cloud private endpoint.
