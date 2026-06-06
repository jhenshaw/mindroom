# K8s Egress Report

## Scope

Checked Helm NetworkPolicy egress for runtime dedicated workers and hosted instance pods.
Touched only chart policies, values, docs, and Helm render tests.

## Validated Findings

- EGRESS-EGRESS-1 real.
  `cluster/k8s/runtime/templates/networkpolicy.yaml` selected dedicated worker pods but declared only `policyTypes: [Ingress]`, so worker egress was uncontrolled when a CNI enforced NetworkPolicy.
- EGRESS-EGRESS-2 / INFRA-INFRA-1 real.
  `cluster/k8s/instance/templates/networkpolicy.yaml` allowed egress to ports `80` and `443` without a `to` peer, which meant any destination on those ports, including metadata and internal CIDRs.
- EGRESS-EGRESS-3 fixed at L3/L4 for chart-managed pods.
  Runtime worker egress now default-denies with explicit DNS, runtime, safe public CIDR, and configurable broker/service allow rules.
  Instance egress now uses safe public CIDR allow rules with private, link-local, metadata, multicast, and reserved CIDR exceptions.
- INFRA-INFRA-5 not changed.
  Platform chart has no NetworkPolicy, but adding one safely requires enumerating Supabase, Stripe, model-provider, Kubernetes API, and ingress dependencies.
  That was not a small chart-only fix.

## Changes

- Added runtime worker `Egress` policy type and egress rules for runtime API, DNS, safe public HTTP/HTTPS, and `workers.kubernetes.networkPolicy.extraEgress`.
- Replaced hosted instance bare `80/443` egress with `ipBlock` public CIDR plus configurable exceptions.
- Added hosted instance `networkPolicy.workerExtraEgress` for worker-only private broker egress.
- Added hosted instance `networkPolicy.controlPlaneExtraEgress` for primary-only required private services such as private Kubernetes API-server CIDRs.
- Added Helm render tests for no bare HTTP/HTTPS egress, configurable CIDR exceptions, runtime worker egress default-deny, and source-scoped extra egress.
- Updated Kubernetes and sandbox proxy docs.

## Verification

Passed.
`uv` was not available in the source worktree, so pytest used the existing c31e `.venv` while running from the clean PR clone.

```bash
/Users/bas.nijholt/.codex/worktrees/c31e/mindroom/.venv/bin/pytest tests/test_helm_instance_worker_isolation.py -k "network_policy or egress" -n 0 --no-cov -v
# 9 passed, 30 deselected

/Users/bas.nijholt/.codex/worktrees/c31e/mindroom/.venv/bin/pytest tests/test_helm_instance_worker_isolation.py -n 0 --no-cov -v
# 39 passed

helm lint cluster/k8s/instance && helm lint cluster/k8s/runtime
# 2 charts linted, 0 charts failed

helm template mindroom-demo cluster/k8s/instance --set workerBackend=kubernetes --set storageAccessMode=ReadWriteMany >/tmp/mindroom-instance-render-pr.yaml
helm template mindroom-runtime cluster/k8s/runtime --set workers.backend=kubernetes --set workers.sandbox.proxyToken.value=test-token --set eventCache.postgres.auth.password=test-password >/tmp/mindroom-runtime-render-pr.yaml
# rendered 1287 instance lines and 611 runtime lines

PATH=/tmp/mindroom-uv-shim:$PATH /Users/bas.nijholt/.codex/worktrees/c31e/mindroom/.venv/bin/pre-commit run --files cluster/k8s/instance/templates/networkpolicy.yaml cluster/k8s/instance/values.yaml cluster/k8s/runtime/templates/networkpolicy.yaml cluster/k8s/runtime/values.yaml docs/deployment/kubernetes.md docs/deployment/sandbox-proxy.md skills/mindroom-docs/references/llms-full.txt skills/mindroom-docs/references/page__deployment__kubernetes__index.md skills/mindroom-docs/references/page__deployment__sandbox-proxy__index.md tests/test_helm_instance_worker_isolation.py .claude/REPORT-k8s-egress.md
# passed
```
