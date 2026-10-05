"""Regression checks against the YAML produced by Helm."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


CHART = Path(__file__).resolve().parents[1]


def render(values, validate=True):
    with tempfile.TemporaryDirectory() as directory:
        values_file = Path(directory) / "values.yaml"
        values_file.write_text(yaml.safe_dump(values))
        result = subprocess.run(
            ["helm", "template", "test", str(CHART), "--namespace", "istio-system",
             "--values", str(values_file)],
            check=True, capture_output=True, text=True,
        )
    if validate and result.stdout.strip() and shutil.which("istioctl"):
        validation = subprocess.run(
            ["istioctl", "validate", "--filename", "-"],
            input=result.stdout, capture_output=True, text=True,
        )
        if validation.returncode:
            raise AssertionError(
                f"Istio validation failed:\n{validation.stdout}\n{validation.stderr}"
            )
    return [resource for resource in yaml.safe_load_all(result.stdout) if resource]


class RenderTests(unittest.TestCase):
    def test_default_values_render_no_resources(self):
        self.assertEqual(render({}), [])

    def test_unscoped_rule_keeps_existing_name_and_policy(self):
        policy = {"loadBalancer": {"simple": "ROUND_ROBIN"}}
        subsets = [{"name": "v1", "labels": {"version": "v1"}}]
        rule = render({"destinationrule": [{
            "name": "backend", "host": "backend.default.svc.cluster.local",
            "trafficPolicy": policy, "subsets": subsets,
        }]})[0]
        self.assertEqual(rule["metadata"]["name"], "backend-destinationrule")
        self.assertEqual(rule["spec"], {
            "host": "backend.default.svc.cluster.local",
            "trafficPolicy": policy, "subsets": subsets,
        })

    def test_scoped_tls_rule_uses_configured_namespace(self):
        tls = {
            "mode": "SIMPLE",
            "caCertificates": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
            "sni": "kubernetes.default.svc.cluster.local",
            "subjectAltNames": ["kubernetes.default.svc.cluster.local"],
        }
        selector = {"matchLabels": {"app": "istio-ingressgateway"}}
        rule = render({"namespace": "gateways", "destinationrule": [{
            "name": "api",
            "host": "kubernetes.default.svc.cluster.local",
            "exportTo": ["."], "workloadSelector": selector,
            "trafficPolicy": {"tls": tls},
        }]})[0]
        self.assertEqual(rule["metadata"]["name"], "api-destinationrule")
        self.assertEqual(rule["metadata"]["namespace"], "gateways")
        self.assertEqual(rule["spec"], {
            "host": "kubernetes.default.svc.cluster.local",
            "exportTo": ["."], "workloadSelector": selector,
            "trafficPolicy": {"tls": tls},
        })

    def test_scoping_does_not_leak_between_rules(self):
        rules = render({"destinationrule": [
            {"name": "scoped", "host": "one.example.com", "exportTo": ["."],
             "workloadSelector": {"matchLabels": {"app": "gateway"}}},
            {"host": "two.example.com"},
        ]})
        self.assertEqual(len(rules), 2)
        self.assertEqual(rules[0]["spec"]["exportTo"], ["."])
        self.assertEqual(rules[1]["metadata"]["name"], "test-destinationrule")
        self.assertEqual(rules[1]["spec"], {"host": "two.example.com"})

    def test_empty_optional_fields_are_omitted(self):
        rule = render({"destinationrule": [{
            "host": "api.example.com",
            "exportTo": [], "workloadSelector": {},
        }]})[0]
        self.assertEqual(rule["metadata"]["name"], "test-destinationrule")
        self.assertEqual(rule["spec"], {"host": "api.example.com"})

    def test_http_faults_preserve_routes_and_order(self):
        destination = [{"destination": {
            "host": "backend.default.svc.cluster.local", "port": {"number": 8080},
        }}]
        routes = [
            {"match": [{"uri": {"prefix": "/blocked"}}],
             "fault": {"abort": {"percentage": {"value": 100}, "httpStatus": 403}},
             "route": destination},
            {"match": [{"uri": {"prefix": "/slow"}}],
             "fault": {"delay": {"percentage": {"value": 25}, "fixedDelay": "1s"}},
             "route": destination},
            {"match": [{"uri": {"prefix": "/"}}], "route": destination},
        ]
        resources = render({"ingress": {
            "name": "backend", "hosts": ["backend.example.com"],
            "gateways": [{"type": "internal", "gateway_selector": "istio-ingressgateway",
                          "ports": [{"number": 80, "name": "http", "protocol": "HTTP"}]}],
            "virtualservice": {"http": routes},
        }})
        virtualservice = next(r for r in resources if r["kind"] == "VirtualService")
        self.assertEqual(virtualservice["spec"]["http"], routes)
        self.assertEqual(virtualservice["spec"]["gateways"], ["backend-gateway-internal"])

    def test_full_fixture_renders_all_resource_kinds(self):
        resources = render(yaml.safe_load((CHART / "ci" / "full.yaml").read_text()))
        self.assertEqual({r["kind"] for r in resources}, {
            "Gateway", "VirtualService", "ServiceEntry", "DestinationRule",
            "AuthorizationPolicy", "PeerAuthentication", "RequestAuthentication",
        })
        rules = [r for r in resources if r["kind"] == "DestinationRule"]
        self.assertEqual(len(rules), 2)
        self.assertEqual({r["metadata"]["name"] for r in rules},
                         {"my-service-destinationrule", "apiserver-ingress-destinationrule"})

    def test_complete_http_routes_are_passed_through(self):
        routes = [
            {"name": "fixed-response", "match": [{"uri": {"exact": "/blocked"}}],
             "directResponse": {"status": 403, "body": {"string": "Forbidden"}}},
            {"name": "redirect", "match": [{"uri": {"prefix": "/old"}}],
             "redirect": {"uri": "/new", "redirectCode": 301}},
            {"name": "mirrored-catch-all", "route": [{"destination": {
                "host": "api.default.svc.cluster.local", "port": {"number": 80},
             }}], "mirror": {"host": "shadow.default.svc.cluster.local",
                             "port": {"number": 80}}, "mirrorPercentage": {"value": 10}},
        ]
        virtualservice = render({"ingress": {
            "hosts": ["api.example.com"],
            "virtualservice": {"gateways": ["mesh"], "http": routes},
        }})[0]
        self.assertEqual(virtualservice["spec"]["http"], routes)

    def test_health_probe_precedes_supplied_routes(self):
        routes = [{"directResponse": {"status": 503}}]
        virtualservice = render({"ingress": {
            "hosts": ["api.example.com"],
            "virtualservice": {"gateways": ["mesh"], "http": routes,
                               "health": {"enabled": True, "host": "gateway",
                                          "port": 15021}},
        }})[0]
        actual = virtualservice["spec"]["http"]
        self.assertEqual(actual[0], {
            "match": [{"uri": {"prefix": "/health"}}],
            "rewrite": {"uri": "/healthz/ready"},
            "route": [{"destination": {"host": "gateway", "port": {"number": 15021}}}],
        })
        self.assertEqual(actual[1:], routes)

    def test_health_probe_can_be_the_only_route(self):
        virtualservice = render({"ingress": {
            "hosts": ["api.example.com"], "virtualservice": {
                "gateways": ["mesh"], "http": [], "health": {"enabled": True},
            },
        }})[0]
        self.assertEqual(len(virtualservice["spec"]["http"]), 1)

    def test_explicit_empty_policy_spec_overrides_inherited_allow_rules(self):
        policy = render({"authorizationPolicy": [{
            "name": "allow-nothing", "spec": {}, "action": "ALLOW",
            "selector": {"matchLabels": {"app": "api"}}, "rules": [{}],
        }]})[0]
        self.assertEqual(policy["spec"], {})

    def test_explicit_policy_spec_overrides_convenience_fields(self):
        raw_spec = {"action": "DENY", "rules": [{"to": [{"operation": {
            "methods": ["POST"],
        }}]}]}
        policy = render({"authorizationPolicy": [{
            "name": "deny-post", "spec": raw_spec, "action": "ALLOW", "rules": [{}],
        }]})[0]
        self.assertEqual(policy["spec"], raw_spec)

    def test_policy_without_spec_keeps_convenience_fields(self):
        spec = {"selector": {"matchLabels": {"app": "api"}},
                "action": "ALLOW", "rules": [{}]}
        policy = render({"authorizationPolicy": [{"name": "allow-api", **spec}]})[0]
        self.assertEqual(policy["spec"], spec)

    def test_null_policy_spec_keeps_convenience_fields(self):
        spec = {"selector": {"matchLabels": {"app": "api"}},
                "action": "ALLOW", "rules": [{"to": [{"operation": {"methods": ["GET"]}}]}]}
        policy = render({"authorizationPolicy": [{
            "name": "allow-get", "spec": None, **spec,
        }]})[0]
        self.assertEqual(policy["spec"], spec)

    def test_egress_gateway_only_adds_tls_to_tls_protocols(self):
        ports = [
            {"number": 80, "name": "http", "protocol": "HTTP"},
            {"number": 5432, "name": "tcp", "protocol": "TCP"},
            {"number": 443, "name": "tls", "protocol": "TLS"},
            {"number": 8443, "name": "https", "protocol": "HTTPS"},
        ]
        resources = render({"egress": [{
            "name": "mixed", "hosts": ["mixed.example.com"], "ports": ports,
            "location": "MESH_EXTERNAL", "resolution": "DNS",
            "gateways": [{"type": "egress", "gateway_selector": "istio-egressgateway"}],
        }]})
        gateway = next(r for r in resources if r["kind"] == "Gateway")
        servers = gateway["spec"]["servers"]
        self.assertEqual([server["port"] for server in servers], ports)
        self.assertNotIn("tls", servers[0])
        self.assertNotIn("tls", servers[1])
        self.assertEqual(servers[2]["tls"], {"mode": "PASSTHROUGH"})
        self.assertEqual(servers[3]["tls"], {"mode": "PASSTHROUGH"})


if __name__ == "__main__":
    unittest.main()
