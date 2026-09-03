import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.policies.registry import build_seed_plan, render_seed_sql, validate_seed
from tools.runtime import policy_config


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "project/policies/active-document-workset-v1.json"


def payload():
    return json.loads(SOURCE.read_text(encoding="utf-8"))


class PolicyRegistryContractTests(unittest.TestCase):
    def test_personal_scope_preserves_other_policy_settings(self):
        current = json.loads(policy_config.DEFAULT_SOURCE.read_text(encoding="utf-8"))
        plan = build_seed_plan(current, environment="acceptance")
        old = build_seed_plan(payload(), environment="acceptance")
        self.assertNotEqual(plan["id"], old["id"])
        self.assertEqual("active-document-workset-v2", plan["policy_version"])
        self.assertEqual(
            {k: v for k, v in old["configuration"].items() if k != "source_roots"},
            {k: v for k, v in plan["configuration"].items() if k != "source_roots"},
        )
        roots = plan["configuration"]["source_roots"]
        def included(path):
            return any(path == root or path.startswith(root + "/") for root in roots)
        for path in (
            "/volume1/data/import/cloud/onedrive/current/Documenten/example.pdf",
            "/volume1/data/Persoonlijk/Actief/Wonen/example.pdf",
            "/volume1/data/Persoonlijk/Inactief/Te beoordelen/example.pdf",
            "/volume1/data/Persoonlijk/Actief/Te beoordelen/example.pdf",
            "/volume1/data/Persoonlijk/Te beoordelen/example.pdf",
        ):
            self.assertTrue(included(path), path)
        for path in (
            "/volume1/data/.core/quarantaine/example.pdf",
            "/volume1/data/Persoonlijk/Actief-extra/example.pdf",
            "/volume1/data/Other/example.pdf",
        ):
            self.assertFalse(included(path), path)

    def test_seed_contract_is_normalized_and_stable(self):
        first = build_seed_plan(payload(), environment="acceptance")
        second = build_seed_plan(payload(), environment="acceptance")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["configuration_checksum"], second["configuration_checksum"])
        self.assertEqual(9, first["configuration"]["activity_window_months"])
        self.assertEqual(["docx", "pdf", "xlsx"], first["configuration"]["extensions"])
        self.assertEqual("acceptance", first["environment"])

    def test_oap_environments_are_supported_without_test_environment(self):
        for environment in ("development", "acceptance", "production"):
            with self.subTest(environment=environment):
                self.assertEqual(environment, validate_seed(payload(), environment=environment)["environment"])
        with self.assertRaisesRegex(ValueError, "development, acceptance or production"):
            validate_seed(payload(), environment="test")

    def test_safety_contract_rejects_non_golden_and_atime_activity(self):
        invalid = payload()
        invalid["configuration"]["golden_records_only"] = False
        with self.assertRaisesRegex(ValueError, "golden_records_only"):
            validate_seed(invalid, environment="acceptance")
        invalid = payload()
        invalid["configuration"]["activity_sources"].append("filesystem_atime")
        with self.assertRaisesRegex(ValueError, "activity_sources"):
            validate_seed(invalid, environment="acceptance")

    def test_seed_sql_is_idempotent_and_checks_provenance(self):
        sql = render_seed_sql(build_seed_plan(payload(), environment="acceptance"))
        self.assertIn("INSERT INTO public.policy_versions", sql)
        self.assertIn("ON CONFLICT DO NOTHING", sql)
        self.assertIn("policy seed provenance validation failed", sql)
        self.assertIn("::jsonb", sql)
        self.assertTrue(sql.startswith("BEGIN;"))
        self.assertTrue(sql.endswith("COMMIT;\n"))


class PolicyRegistryMigrationTests(unittest.TestCase):
    def test_migration_is_immutable_and_resolves_current_policy(self):
        migration = (ROOT / "database/migrations/20260810_add_policy_registry.sql").read_text("utf-8")
        rollback = (ROOT / "database/migrations/rollback/20260810_add_policy_registry.sql").read_text("utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS public.policy_versions", migration)
        self.assertIn("CREATE TRIGGER policy_versions_immutable", migration)
        self.assertIn("BEFORE UPDATE OR DELETE", migration)
        self.assertIn("CREATE OR REPLACE VIEW public.v_current_policies", migration)
        self.assertIn("PARTITION BY p.policy_code, p.environment", migration)
        self.assertIn("DROP TABLE IF EXISTS public.policy_versions", rollback)

    def test_core_cli_exposes_explicit_environment_seed(self):
        cli = (ROOT / "tools/runtime/core").read_text("utf-8")
        self.assertIn("core policy seed --environment development|acceptance|production", cli)
        self.assertIn("sh ./tools/runtime/policy-config seed", cli)

    def test_runtime_dry_run_writes_plan_without_database_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(policy_config, "ROOT", root), mock.patch.object(
                policy_config, "apply_sql"
            ) as apply:
                result = policy_config.main([
                    "seed", "--source", str(SOURCE), "--environment", "acceptance", "--dry-run",
                ])
            plans = list((root / "project/exports/policies").glob("policy-seed-*.json"))
        self.assertEqual(0, result)
        self.assertEqual(1, len(plans))
        apply.assert_not_called()


if __name__ == "__main__":
    unittest.main()
