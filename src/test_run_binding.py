import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from model import Graph
from providers import JSONModel
from run_binding import RunBinding

CONFIGURATION = {"model": "test-model", "endpoint": "https://example.invalid/chat", "key_env": "TEST_KEY"}

def fixture_binding(case, graph=None, roles=("construction", "expression", "checking")):
    temporary = tempfile.TemporaryDirectory()
    case.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    (root / "src").mkdir()
    (root / "src/runtime.py").write_text("# Test fixture source only.\n", encoding="utf-8")
    (root / "procedure.json").write_text(json.dumps({"version": "0.2", "status": "unvalidated reconstruction"}), encoding="utf-8")
    (root / "ledger.bin").write_bytes(b"test ledger bytes")
    (root / "source.txt").write_text("test source", encoding="utf-8")
    if graph is None:
        graph = Graph()
        case.addCleanup(graph.db.close)
    binding = RunBinding.create(graph, repository_root=root, procedure_path="procedure.json", ledger_path="ledger.bin",
        source_paths=["source.txt"], providers={role: dict(CONFIGURATION) for role in roles},
        prompt_templates=JSONModel.prompt_templates(), mode="fixture")
    return graph, binding, root

class BindingTests(unittest.TestCase):
    def test_binding_preserves_declared_status_and_reload(self):
        graph, binding, _ = fixture_binding(self)
        record = binding.inspect()
        self.assertEqual(record["mode"], "fixture")
        self.assertIsNone(record["repository"]["commit"])
        self.assertEqual(record["procedure"]["identity"]["status"], "unvalidated reconstruction")
        self.assertEqual(RunBinding.load(graph, binding.id).verify(), record)
        record["providers"]["construction"]["model"] = "changed"
        self.assertEqual(binding.inspect()["providers"]["construction"]["model"], "test-model")

    def test_changed_input_code_or_new_source_file_rejected(self):
        for filename in ("source.txt", "ledger.bin", "procedure.json", "src/runtime.py", "src/new.py"):
            with self.subTest(filename=filename):
                _, binding, root = fixture_binding(self)
                (root / filename).write_text("changed", encoding="utf-8")
                with self.assertRaises(ValueError): binding.verify()

    def test_binding_evidence_is_append_only(self):
        graph, binding, _ = fixture_binding(self)
        for statement in ("UPDATE run_binding SET digest='fake' WHERE id=?", "DELETE FROM run_binding WHERE id=?"):
            with self.assertRaises(sqlite3.IntegrityError):
                with graph.db: graph.db.execute(statement, (binding.id,))
        self.assertEqual(binding.verify()["id"], binding.id)

    def test_live_without_committed_checkout_rejected(self):
        graph, _, root = fixture_binding(self)
        (root / "configuration.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            RunBinding.create(graph, repository_root=root, procedure_path="procedure.json", ledger_path="ledger.bin",
                              source_paths=["source.txt"], providers={"construction": CONFIGURATION},
                              prompt_templates=JSONModel.prompt_templates(), mode="live", configuration_path="configuration.json")

    def test_live_binding_requires_matching_committed_configuration_and_clean_head(self):
        graph, _, root = fixture_binding(self)
        def git(*args): subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
        config = {"mode": "live", "procedure": "procedure.json", "ledger": "ledger.bin", "sources": ["source.txt"],
                  "providers": {"construction": CONFIGURATION}, "prompt_templates_sha256": JSONModel.templates_digest()}
        (root / "configuration.json").write_text(json.dumps(config), encoding="utf-8")
        git("init", "-q"); git("add", ".")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Fixture baseline")
        parameters = dict(repository_root=root, procedure_path="procedure.json", ledger_path="ledger.bin",
                          source_paths=["source.txt"], providers={"construction": CONFIGURATION},
                          prompt_templates=JSONModel.prompt_templates(), mode="live", configuration_path="configuration.json")
        # A temporary checkout tests Git checks without touching this checkout.
        with self.assertRaises(ValueError): RunBinding.create(graph, **parameters)
        with patch("run_binding.__file__", str(root / "src/run_binding.py")):
            binding = RunBinding.create(graph, **parameters)
            self.assertRegex(binding.verify()["repository"]["commit"], r"^[0-9a-f]{40}$")
            with self.assertRaises(ValueError): RunBinding.create(graph, **parameters, expected_commit="0" * 40)
            parameters["providers"] = {"construction": dict(CONFIGURATION, model="different")}
            with self.assertRaises(ValueError): RunBinding.create(graph, **parameters)
            (root / "src/runtime.py").write_text("# Changed after binding", encoding="utf-8")
            with self.assertRaises(ValueError): binding.verify()
            with self.assertRaises(ValueError): RunBinding.create(graph, **parameters)

if __name__ == "__main__": unittest.main()
