# Changelog

All notable changes to this project are documented in this file.

## [0.3.0] - 2026-10-05

### Added
- Optional native `spec` objects for every resource, with full replacement
  precedence and legacy-value fallback when omitted or null. Existing resource
  naming and automatic ingress/egress generation are preserved.
- `egress[].virtualservice.spec` can declare an egress VirtualService without
  automatically creating gateway resources. Generated egress children can use
  the hosts and ports from a native ServiceEntry spec.
- **Scoped DestinationRules:** optional `exportTo` and `workloadSelector`
  fields on each `destinationrule[]` entry.
- Rendered-resource regression checks on pull requests and before release.
- Offline Istio validation of rendered regression manifests in CI.

### Fixed
- Pass through complete `ingress.virtualservice.http[]` routes, preserving
  fault policies, direct responses, redirects, mirroring, and route names.
- Honor an explicit empty `authorizationPolicy[].spec: {}` override instead
  of falling back to inherited selector/action/rules values. A null spec
  continues to use the convenience fields for compatibility.
- Add TLS PASSTHROUGH only to HTTPS/TLS egress gateway ports; leave plain TCP
  and HTTP-family ports without TLS settings.

## [0.2.0] - 2026-09-09

### Added
- **Egress gateway routing:** `egress[].gateways` list routes mesh traffic
  through an Istio egress gateway (e.g. to `https://gitlab.com`). Presence of
  the list (mirroring the ingress pattern) renders the egress `Gateway`
  resources (`<name>-gateway-<type>`, TLS passthrough) plus a `VirtualService`:
  mesh → egress GW → external host. Per-gateway `host`/`subset` overrides;
  TCP and HTTP ports are routed per-port.

## [0.2.1] - 2026-09-09

### Fixed
- **Egress VirtualService for TLS ports:** generate `tls:` rules with
  `sniHosts` (SNI-matched) instead of `tcp:` port-matched rules. Sidecars
  route external TLS traffic by SNI, so the previous `tcp` rules were never
  applied and traffic bypassed the egress gateway. Verified in-cluster:
  pod → egress gateway → gitlab.com. `tcp:` rules are still emitted for
  plain TCP ports; `http:` for HTTP ports.

## [0.1.1] - 2026-08-03

### Added
- **Security resources:**
  - `AuthorizationPolicy` (ALLOW/DENY, selector or targetRefs, raw spec override)
  - `PeerAuthentication` (mTLS STRICT/PERMISSIVE, port-level overrides)
  - `RequestAuthentication` (JWT validation rules)
- **Multiple gateways per ingress:** `gateway` (single) is now `gateways` (list),
  so one release can declare external + internal gateways.
- **Built-in health probe:** `ingress.virtualservice.health.enabled` injects a
  `/health` → `/healthz/ready` route as the first HTTP rule.
- **Cross-namespace gateway references** via `ingress.gatewayNamespace`.
- **Per-gateway HTTP→HTTPS redirect** via `redirectHttps` on each gateway.
- **VirtualService route fields:** `timeout`, `retries`, `headers`, `corsPolicy`.
- **DestinationRule:** `outlierDetection`, `connectionPool`.
- **Standardized metadata:** Helm recommended labels (`app.kubernetes.io/*`,
  `helm.sh/chart`), `commonLabels`, `commonAnnotations`, configurable `namespace`.
- **CI:** `helm lint` (default + full) and `helm template` validation before release.
- **`ci/full.yaml`** test fixture covering all resources.
- **README** with resources overview, features, and a values table.
- `Chart.yaml` metadata: `type`, `home`, `sources`, `maintainers`, `icon`,
  `annotations`, expanded `keywords`.

### Changed
- `gateway` → **`gateways`** (list).
- `egress` → **`egress[]`** (list, multiple ServiceEntries per release).
- `destinationrule` → **`destinationrule[]`** (list).
- `redirectHttps` moved from ingress level to **per-gateway**.

### Fixed
- `ServiceEntry.ports` rendered an invalid structure (extra `port:` key with
  collapsed fields); now matches the Istio schema (flat `number`/`name`/`protocol`).
- Typo in `values.yaml` example: `htpbin` → `httpbin`.

### Removed
- Top-level `ingress.redirectHttps` (replaced by per-gateway `redirectHttps`).

### ⚠️ Breaking changes
- `gateway` (single) → `gateways` (list).
- `egress` and `destinationrule` are now lists.
- `redirectHttps` moved from ingress level to per-gateway.
- The health probe moved from a manual `http[]` entry to the `health` block.

## [0.1.0] - 2026-04-26

### Added
- Initial chart: Gateway, VirtualService, ServiceEntry, DestinationRule.
- GitHub Actions workflow publishing the chart via chart-releaser.
