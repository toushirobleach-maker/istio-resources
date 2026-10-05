"""Check native specs and legacy values across every resource template."""

import copy
import subprocess
import unittest

import yaml

from test_render import CHART, render


def spec_targets(values):
    """Map the native input objects to their unchanged resource identities."""
    ingress = values["ingress"]
    egress = values["egress"][0]
    return {
        ("Gateway", "api-gateway-internal"): ingress["gateways"][0],
        ("VirtualService", "api-virtualservice"): ingress["virtualservice"],
        ("ServiceEntry", "external-egress"): egress,
        ("Gateway", "external-gateway-egress"): egress["gateways"][0],
        ("VirtualService", "external-egress-virtualservice"): egress["virtualservice"],
        ("DestinationRule", "api-destinationrule"): values["destinationrule"][0],
        ("AuthorizationPolicy", "api"): values["authorizationPolicy"][0],
        ("PeerAuthentication", "api"): values["peerAuthentication"][0],
        ("RequestAuthentication", "api"): values["requestAuthentication"][0],
    }


class SpecTests(unittest.TestCase):
    def setUp(self):
        self.values = yaml.safe_load((CHART / "ci" / "spec.yaml").read_text())

    def test_all_native_specs_override_conflicting_convenience_fields(self):
        expected = spec_targets(self.values)
        actual = {(r["kind"], r["metadata"]["name"]): r for r in render(self.values)}
        self.assertEqual(set(actual), set(expected))
        for identity, entry in expected.items():
            with self.subTest(resource=identity):
                self.assertEqual(actual[identity]["spec"], entry["spec"])
                self.assertEqual(actual[identity]["metadata"]["namespace"], "istio-system")

    def test_explicit_empty_specs_are_not_replaced_or_merged(self):
        # Empty specs are not valid for every Istio kind. Check the chart's
        # pass-through contract here; valid manifests are validated elsewhere.
        expected = spec_targets(self.values)
        for entry in expected.values():
            entry["spec"] = {}
        actual = render(self.values, validate=False)
        self.assertEqual(len(actual), len(expected))
        for resource in actual:
            with self.subTest(kind=resource["kind"], name=resource["metadata"]["name"]):
                self.assertEqual(resource["spec"], {})

    def test_null_specs_preserve_all_legacy_resources(self):
        values = yaml.safe_load((CHART / "ci" / "full.yaml").read_text())
        baseline = render(values)
        values["ingress"]["virtualservice"]["spec"] = None
        for gateway in values["ingress"]["gateways"]:
            gateway["spec"] = None
        for entry in values["egress"]:
            entry["spec"] = None
            entry["virtualservice"] = {"spec": None}
            for gateway in entry.get("gateways", []):
                gateway["spec"] = None
        for key in ("destinationrule", "authorizationPolicy", "peerAuthentication",
                    "requestAuthentication"):
            for entry in values[key]:
                entry["spec"] = None
        self.assertEqual(render(values), baseline)

    def test_legacy_values_keep_the_pre_spec_resource_snapshot(self):
        values = yaml.safe_load((CHART / "ci" / "full.yaml").read_text())
        actual = render(values)
        for resource in actual:
            resource["metadata"]["labels"].pop("helm.sh/chart", None)
        expected = yaml.safe_load((CHART / "ci" / "legacy-rendered.yaml").read_text())
        self.assertEqual(actual, expected)

    def test_generated_egress_children_use_native_service_entry_hosts_and_ports(self):
        entry = self.values["egress"][0]
        del entry["virtualservice"]
        del entry["gateways"][0]["spec"]
        entry["gateways"][0]["gateway_selector"] = "istio-egressgateway"
        resources = render({"egress": [entry]})
        gateway = next(r for r in resources if r["kind"] == "Gateway")
        server = gateway["spec"]["servers"][0]
        self.assertEqual(server["hosts"], entry["spec"]["hosts"])
        self.assertEqual(server["port"], entry["spec"]["ports"][0])
        vs = next(r for r in resources if r["kind"] == "VirtualService")
        self.assertEqual(vs["spec"]["hosts"], entry["spec"]["hosts"])
        self.assertEqual(vs["spec"]["tls"][1]["route"][0]["destination"]["host"],
                         "external.example.com")

    def test_native_egress_virtualservice_can_render_without_generated_gateways(self):
        entry = self.values["egress"][0]
        del entry["gateways"]
        raw = entry["virtualservice"]["spec"]
        raw["gateways"] = ["mesh"]
        raw["tls"] = raw["tls"][:1]
        resources = render({"egress": [entry]})
        self.assertEqual({r["kind"] for r in resources}, {"ServiceEntry", "VirtualService"})
        vs = next(r for r in resources if r["kind"] == "VirtualService")
        self.assertEqual(vs["spec"], raw)

    def test_invalid_spec_types_fail_instead_of_being_silently_ignored(self):
        for identity in spec_targets(self.values):
            values = copy.deepcopy(self.values)
            spec_targets(values)[identity]["spec"] = []
            with self.subTest(resource=identity):
                with self.assertRaises(subprocess.CalledProcessError) as error:
                    render(values)
                self.assertIn("spec must be a YAML object", error.exception.stderr)

    def test_null_spec_alone_does_not_create_an_ingress_virtualservice(self):
        self.assertEqual(render({"ingress": {"virtualservice": {"spec": None}}}), [])


if __name__ == "__main__":
    unittest.main()
