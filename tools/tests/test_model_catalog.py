import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools import model_catalog


class ModelCatalogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.catalog = json.loads((model_catalog.ROOT / "models/catalog.json").read_text())
        self.template = json.loads((model_catalog.ROOT / "models/providers.example.json").read_text())
        (self.root / "models").mkdir()
        sources = {}
        for role in self.catalog["capabilities"]:
            for adapter in role["adapters"]:
                sources.setdefault(adapter["source"], set()).add(adapter["symbol"])
            for source in role["configuration_sources"]:
                sources.setdefault(source, set())
        for name, symbols in sources.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            # Importing this fixture would fail. The checker must parse, never load it.
            path.write_text("raise RuntimeError('Do not import model providers')\n" +
                            "".join(f"class {symbol}: pass\n" for symbol in sorted(symbols)))
        self.write()

    def write(self):
        (self.root / "models/catalog.json").write_text(json.dumps(self.catalog))
        (self.root / "models/providers.example.json").write_text(json.dumps(self.template))

    def test_real_catalog_resolves_all_adapters_without_model_imports(self):
        result = model_catalog.verify()
        self.assertEqual(len(result["capabilities"]), 13)
        self.assertEqual(result["availability"], "not_probed")
        self.assertEqual(result["model_quality"], "not_evaluated")
        self.assertFalse(result["providers_contacted"])
        self.assertFalse(result["runtime_controller"])

    def test_checker_parses_source_without_executing_provider_modules(self):
        result = model_catalog.verify(self.root)
        self.assertFalse(result["weights_loaded"])
        self.assertEqual(result["status"], "source_inventory_verified")

    def test_outdated_adapter_symbol_is_rejected(self):
        self.catalog["capabilities"][4]["adapters"][0]["symbol"] = "LocalMemoryNarrativeProvider"
        self.write()
        with self.assertRaisesRegex(model_catalog.CatalogError, "adapter_symbol_missing"):
            model_catalog.verify(self.root)

    def test_template_cannot_enable_or_embed_installation_or_secrets(self):
        clean = copy.deepcopy(self.template)
        for field, value, reason in (("enabled", True, "template_adapter_mismatch"),
                                    ("endpoint", "http://private.invalid", "template_contains_installation"),
                                    ("token", "synthetic-secret", "template_fields")):
            with self.subTest(field=field):
                self.template = copy.deepcopy(clean)
                self.template["providers"][0][field] = value
                self.write()
                with self.assertRaisesRegex(model_catalog.CatalogError, reason):
                    model_catalog.verify(self.root)

    def test_capability_and_selection_contracts_must_match(self):
        self.template["providers"][0]["contract"] = "unrelated-vector-contract"
        self.write()
        with self.assertRaisesRegex(model_catalog.CatalogError, "template_adapter_mismatch"):
            model_catalog.verify(self.root)

    def test_missing_role_and_duplicate_role_are_rejected(self):
        clean = copy.deepcopy(self.catalog)
        for replacement in (clean["capabilities"][:-1], clean["capabilities"][:-1] + [clean["capabilities"][0]]):
            self.catalog["capabilities"] = replacement
            self.write()
            with self.assertRaisesRegex(model_catalog.CatalogError, "capability_inventory"):
                model_catalog.verify(self.root)

    def test_provider_reference_cannot_escape_or_follow_symlink(self):
        self.catalog["capabilities"][0]["adapters"][0]["source"] = "server/../outside.py"
        self.write()
        with self.assertRaisesRegex(model_catalog.CatalogError, "unsafe_source_path"):
            model_catalog.verify(self.root)
        self.catalog["capabilities"][0]["adapters"][0]["source"] = "server/linked.py"
        (self.root / "server/linked.py").symlink_to(model_catalog.ROOT / "tools/model_catalog.py")
        self.write()
        with self.assertRaisesRegex(model_catalog.CatalogError, "symlink_source"):
            model_catalog.verify(self.root)

    def test_weights_in_source_model_directory_are_rejected(self):
        (self.root / "models/unexpected.onnx").write_bytes(b"synthetic weight marker")
        with self.assertRaisesRegex(model_catalog.CatalogError, "weights_in_source_directory"):
            model_catalog.verify(self.root)

    def test_duplicate_json_keys_are_rejected(self):
        (self.root / "models/catalog.json").write_text('{"schema":1,"schema":1}')
        with self.assertRaisesRegex(model_catalog.CatalogError, "duplicate_json_key"):
            model_catalog.verify(self.root)


if __name__ == "__main__":
    unittest.main()
