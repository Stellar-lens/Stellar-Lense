# Stellar Lense Helm Charts

This directory contains the Helm chart and values files used to deploy
Stellar Lense on Kubernetes.

## Contents

- **`stellar_lense/`** — The official Stellar Lense Helm chart.
  - `Chart.yaml` — Chart metadata (name, version, description)
  - `values.yaml` — Default configuration: replica count, image, service,
    ingress, API/worker probes and resources, autoscaling, ConfigMap settings,
    secrets, persistence, ServiceAccount, and cost/capacity configuration
  - `templates/` — Kubernetes manifests rendered by the chart (deployments,
    ConfigMap, Secret, Service, Ingress, HPA, PVC, ServiceAccount, cost config)
- **`chaos-mesh-values.yaml`** — Values file for deploying Chaos Mesh
  (`pingcap/chaos-mesh`) alongside the chart for chaos-engineering tests.

## Quick start

```bash
helm install stellar_lense ./helm/stellar_lense
```

Override defaults with `--set` (e.g. `--set ingress.enabled=true`) or a custom
values file:

```bash
helm install stellar_lense ./helm/stellar_lense -f my-values.yaml
```

## Further reading

- [docs/kubernetes_deployment.md](../docs/kubernetes_deployment.md) — Full deployment guide and parameter reference
- [docs/cost_and_capacity.md](../docs/cost_and_capacity.md) — Cost and capacity configuration
- [docs/observability.md](../docs/observability.md) — Metrics, logging, and alerting
