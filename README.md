# istio-resources

A Helm chart to manage Istio resources declaratively from a single `values.yaml`.

It renders the most common Istio CRDs — Gateway, VirtualService, ServiceEntry,
DestinationRule, AuthorizationPolicy, PeerAuthentication, RequestAuthentication —
with sensible helpers (labels, namespaces, health probes, redirects, etc.) so you
don't hand-write boilerplate per project.

## Resources

| Resource | Values key | Notes |
|---|---|---|
| `Gateway` | `ingress.gateways[]` | One or more gateways (e.g. external + internal) |
| `VirtualService` | `ingress.virtualservice` | Routes; optional built-in health probe, retries, timeout, CORS |
| `ServiceEntry` | `egress[]` | List of external/mesh service entries; optional egress-gateway routing |
| `DestinationRule` | `destinationrule[]` | Load balancing, subsets, outlier detection, connection pools |
| `AuthorizationPolicy` | `authorizationPolicy[]` | ALLOW/DENY rules; selector or targetRefs |
| `PeerAuthentication` | `peerAuthentication[]` | mTLS mode (STRICT/PERMISSIVE), port-level overrides |
| `RequestAuthentication` | `requestAuthentication[]` | JWT validation rules |

## Quick start

```yaml
ingress:
  name: git
  hosts:
    - git.example.com
  gateways:
    - type: external
      gateway_selector: istio-ingress-gateway-external
      ports:
        - number: 443
          name: https
          protocol: HTTPS
              tls:
                mode: SIMPLE
                credentialName: git-tls
        - number: 80
          name: http
          protocol: HTTP
  virtualservice:
    health:
      enabled: true
    http:
      - route:
          - destination:
              host: httpbin.default.svc.cluster.local
              port:
                number: 3000
```

## Features

### Multiple gateways per ingress
Define several gateways (e.g. public + internal) under `ingress.gateways`.
Each produces `<name>-gateway-<type>`, and the VirtualService automatically
references all of them.

### HTTP → HTTPS redirect
Set `redirectHttps: true` on an individual gateway to render its HTTP (non-TLS)
ports as redirect servers (`tls.httpsRedirect: true`) instead of plain HTTP.
The flag is **per-gateway**, so the external gateway can redirect to HTTPS
while the internal gateway keeps serving plain HTTP.

### Built-in health probe
`ingress.virtualservice.health.enabled: true` injects a `/health` →
`/healthz/ready` route as the **first** HTTP rule (before your `http[]`),
routing to the ingress gateway's health endpoint by default. Override
`health.host` / `health.port` for non-default setups.

### Cross-namespace gateway references
When `ingress.gatewayNamespace` is set, the VirtualService references the
created gateways as `<gatewayNamespace>/<name>-gateway-<type>` (Istio's
required format for cross-namespace refs). Omit it for same-namespace refs.

### Egress gateway routing
Route mesh traffic to an external host through an Istio egress gateway.
The pattern mirrors ingress: **presence of `gateways`** creates the resources —
no separate enable flags.

```yaml
egress:
  - name: gitlab
    hosts:
      - gitlab.com
    ports:
      - number: 443
        name: https
        protocol: TLS
    location: MESH_EXTERNAL
    resolution: DNS
    gateways:
      - type: egress                       # Gateway: gitlab-gateway-egress
        gateway_selector: istio-egressgateway
```

This renders, alongside the `ServiceEntry`, the egress `Gateway`
(`<name>-gateway-<type>`, servers generated from the entry's ports/hosts, TLS
passthrough for non-HTTP ports) and a `VirtualService` with two rules:
mesh → egress gateway, and egress gateway → external host.

Per-gateway options:
- `host` — egress gateway service host to route traffic to
  (default `istio-egressgateway.istio-system.svc.cluster.local`)
- `subset` — route to a DestinationRule subset on the gateway host

### List-valued resources
`egress`, `destinationrule`, `authorizationPolicy`, `peerAuthentication`, and
`requestAuthentication` are **lists**, so one release can declare several of
each (multiple egress endpoints, multiple policies, etc.).

### Scoped DestinationRules

Set `destinationrule[].spec.workloadSelector` to apply an upstream policy only to
matching client workloads in the rule's namespace. Set `exportTo: ["."]` to
limit visibility to that namespace. For example, originate TLS from an
ingress gateway without changing other clients of the same service:

```yaml
destinationrule:
  - name: apiserver-ingress
    spec:
      host: kubernetes.default.svc.cluster.local
      exportTo: ["."]
      workloadSelector:
        matchLabels:
          app: istio-ingressgateway
      trafficPolicy:
        tls:
          mode: SIMPLE
          caCertificates: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
          sni: kubernetes.default.svc.cluster.local
          subjectAltNames:
            - kubernetes.default.svc.cluster.local
```

The CA file must be readable in the selected gateway pods. Verify the server
certificate contains the configured subject alternative name. The rule and
selected workloads must share a namespace; selectors do not span namespaces.

Omitting `exportTo` and `workloadSelector` keeps the existing unscoped behavior.

### Native specs for every resource

Use `spec` to pass a complete native Istio resource specification through
unchanged. The chart still creates metadata using its existing naming,
namespace, labels, and annotations. This avoids maintaining a second copy of
Istio's API in Helm templates.

| Resource | Native spec location |
|---|---|
| Ingress Gateway | `ingress.gateways[].spec` |
| Ingress VirtualService | `ingress.virtualservice.spec` |
| ServiceEntry | `egress[].spec` |
| Egress Gateway | `egress[].gateways[].spec` |
| Egress VirtualService | `egress[].virtualservice.spec` |
| DestinationRule | `destinationrule[].spec` |
| AuthorizationPolicy | `authorizationPolicy[].spec` |
| PeerAuthentication | `peerAuthentication[].spec` |
| RequestAuthentication | `requestAuthentication[].spec` |

The same rules apply at every location:

- A non-null spec object replaces the entire generated spec. Convenience
  fields, health routes, redirects, and generated gateway references are not
  merged into it. Supply all required native fields explicitly.
- An explicit `spec: {}` is passed through as an empty object. Whether an
  empty spec is valid depends on the Istio resource kind.
- An omitted spec or `spec: null` uses the existing convenience fields and
  automatic generation. Values in the 0.2.1 format need no schema changes
  to use 0.3.0. The bug fixes listed in the changelog still apply.
- Non-object spec values fail Helm rendering with an explicit error.

These rules apply to the final Helm values. Helm's normal merging of multiple
values files still takes place before template rendering.

A spec override affects only its resource. For example, overriding an ingress
VirtualService does not suppress the Gateways declared in `ingress.gateways`.
The chart does not create gateway references or inject a health probe inside
that native VirtualService spec.

For egress, `egress[].spec` overrides the ServiceEntry only. If `gateways` are
also declared, automatic egress Gateway/VirtualService generation uses the
ServiceEntry spec's `hosts` and `ports`. Override each child's own spec to
control it directly. A native `egress[].virtualservice.spec` also creates an
egress VirtualService when no generated gateways are declared.

See [`ci/spec.yaml`](charts/istio-resources/ci/spec.yaml) for a validated example
covering every native spec location. [`ci/full.yaml`](charts/istio-resources/ci/full.yaml)
continues to exercise the existing convenience format.

### HTTP routes

`ingress.virtualservice.http[]` entries are passed through to Istio in full,
including route names, direct responses, redirects, mirroring, fault policies,
headers, and destinations. A route without `match` remains a catch-all route
according to Istio semantics. When enabled, the built-in health probe remains
the first route, followed by the supplied HTTP routes in their original order.

### AuthorizationPolicy spec overrides

An explicit `authorizationPolicy[].spec` takes precedence over the convenience
fields (`selector`, `targetRefs`, `action`, `rules`), including an empty object.
Use `spec: {}` for an allow-nothing policy. Without `spec`, or with `spec: null`,
the chart renders the convenience fields as before.

### Standardized metadata
Every resource gets Helm recommended labels (`app.kubernetes.io/*`,
`helm.sh/chart`) plus optional `commonLabels` and `commonAnnotations`. Use
`namespace` to place resources outside the release namespace.

## Values

| Key | Type | Default | Description |
|---|---|---|---|
| `nameOverride` | string | `""` | Override the chart name in resource names/labels |
| `namespace` | string | `""` | Namespace for all resources (defaults to release namespace) |
| `commonLabels` | object | `{}` | Labels added to every resource |
| `commonAnnotations` | object | `{}` | Annotations added to every resource |
| `ingress.name` | string | `""` | Base name for gateway/VS (defaults to release name) |
| `ingress.hosts` | list | `[]` | Hosts shared by gateway servers and the VirtualService |
| `ingress.gatewayNamespace` | string | `""` | Namespace prefix for cross-namespace gateway refs |
| `ingress.redirectHttps` | bool | `false` | *(removed — now per-gateway)* |
| `ingress.gateways[]` | list | `[]` | Gateway definitions (type, gateway_selector, redirectHttps, ports, tls) |
| `ingress.virtualservice.gateways` | list | `[]` | Explicit gateway refs (used when `ingress.gateways` is empty) |
| `ingress.virtualservice.health.enabled` | bool | `false` | Inject `/health` probe as first HTTP rule |
| `ingress.virtualservice.health.host` | string | `istio-ingress-gateway` | Health destination host |
| `ingress.virtualservice.health.port` | int | `15021` | Health destination port |
| `ingress.virtualservice.http[]` | list | `[]` | HTTP routes (match/rewrite/redirect/route/timeout/retries/headers/fault/corsPolicy) |
| `ingress.virtualservice.tcp[]` | list | `[]` | TCP routes |
| `egress[]` | list | `[]` | ServiceEntry definitions |
| `destinationrule[]` | list | `[]` | DestinationRule definitions |
| `destinationrule[].exportTo` | list | unset | Namespaces to which the rule is exported |
| `destinationrule[].workloadSelector` | object | unset | Select matching client workloads in the rule's namespace |
| `authorizationPolicy[]` | list | `[]` | AuthorizationPolicy definitions |
| `peerAuthentication[]` | list | `[]` | PeerAuthentication definitions |
| `requestAuthentication[]` | list | `[]` | RequestAuthentication definitions |

See [`charts/istio-resources/values.yaml`](charts/istio-resources/values.yaml)
for fully commented examples of every resource.

## CI

The GitHub Actions workflow (`.github/workflows/release.yml`) runs `helm lint`
on default and full-feature values and rendered-resource regression checks
on pull requests and pushes to `main`. CI also validates rendered test manifests
with `istioctl` 1.28.3, without connecting to a cluster. Only pushes to `main`
publish charts with chart-releaser.

Run the regression checks locally with Helm, Python, and PyYAML installed:

```sh
python -m unittest discover -s charts/istio-resources/ci -p 'test_*.py' -v
```

If `istioctl` is available on `PATH`, these tests also run `istioctl validate`
on every non-empty rendered manifest. CI installs it before running the tests.
