"""Immutable execution inputs and provider-call evidence (BR-08.02, CE-03).

These are persistence helpers for Execution, not a second lifecycle engine.
Fixture bindings are deliberately distinguishable from committed live runs.
"""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid
from urllib.parse import urlsplit

PARAGRAPH_ADDENDUM = 'procedures/addenda/paragraph-pangram-v0.1.json'
PARAGRAPH_ADDENDUM_ID = 'AA-PROCEDURE-ADDENDUM-PARAGRAPH-PANGRAM-001'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def contains_credential(value, credential, depth=0):
    """Check parsed JSON too: a provider can escape a secret in nested content."""
    if depth > 64:
        raise ValueError("Provider response nesting exceeds safe inspection depth")
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        if credential in value:
            return True
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError, RecursionError):
            return False
        if decoded != value:
            return contains_credential(decoded, credential, depth + 1)
        return False
    if isinstance(value, dict):
        return any(contains_credential(key, credential, depth + 1)
                   or contains_credential(item, credential, depth + 1)
                   for key, item in value.items())
    if isinstance(value, (tuple, list)):
        return any(contains_credential(item, credential, depth + 1) for item in value)
    return False


def _now():
    return datetime.now(timezone.utc).isoformat()


def validate_provider(configuration):
    if not isinstance(configuration, dict) or set(configuration) != {"model", "endpoint", "key_env"}:
        raise ValueError("Provider requires only model, endpoint and credential environment name")
    if not isinstance(configuration["model"], str) or not configuration["model"].strip():
        raise ValueError("Model identity required")
    endpoint = urlsplit(configuration["endpoint"])
    if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
        raise ValueError("HTTPS endpoint without credentials, query or fragment required")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", configuration["key_env"]):
        raise ValueError("Credential environment variable name required")


def _schema(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS run_binding (
            id TEXT PRIMARY KEY, manifest TEXT NOT NULL, digest TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS provider_invocation (
            id TEXT PRIMARY KEY, binding TEXT NOT NULL REFERENCES run_binding(id),
            provider_role TEXT NOT NULL, operation TEXT NOT NULL,
            request TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS provider_event (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            invocation TEXT NOT NULL REFERENCES provider_invocation(id),
            state TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
        );
    """)
    for table in ("run_binding", "provider_invocation", "provider_event"):
        for operation in ("UPDATE", "DELETE"):
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()}
                BEFORE {operation} ON {table} BEGIN
                SELECT RAISE(ABORT, 'Execution evidence is append-only'); END""")
    db.commit()


def _file(root, value):
    path = Path(value)
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_file():
        raise ValueError("Bound artifact is not a file: " + str(path))
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _label(root, path):
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return str(path)


def _git(root, *arguments):
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError("Live execution requires an accessible committed Git checkout")
    return result.stdout.strip()


def _code(root):
    files = sorted((root / "src").rglob("*.py"))
    if not files:
        raise ValueError("Repository Python source manifest is empty")
    return [_file(root, path) for path in files]


class RunBinding:
    def __init__(self, graph, ident):
        self.g = graph
        self.id = ident

    @classmethod
    def create(cls, graph, *, repository_root, procedure_path, ledger_path,
               source_paths, providers, prompt_templates, mode="live",
               configuration_path=None, expected_commit=None, addenda_paths=()):
        if mode not in {"fixture", "live"}:
            raise ValueError("Explicit live or fixture mode required")
        root = Path(repository_root).resolve()
        if not isinstance(providers, dict) or not providers:
            raise ValueError("Declared providers required")
        for role, configuration in providers.items():
            if not isinstance(role, str) or not role.strip():
                raise ValueError("Provider role required")
            validate_provider(configuration)
        if not isinstance(prompt_templates, dict) or not prompt_templates:
            raise ValueError("Frozen prompt templates required")
        procedure = _file(root, procedure_path)
        specification = json.loads(Path(procedure["path"]).read_text(encoding="utf-8"))
        if not isinstance(specification, dict) or not specification.get("version") or not specification.get("status"):
            raise ValueError("Procedure version and declared validation status required")
        procedure["identity"] = specification
        addenda = [_file(root, path) for path in addenda_paths]
        if len({item['path'] for item in addenda}) != len(addenda):
            raise ValueError('Duplicate procedure addendum')
        for item in addenda:
            identity = json.loads(Path(item['path']).read_text(encoding='utf-8'))
            if not isinstance(identity, dict) or not identity.get('version') or not identity.get('status'):
                raise ValueError('Procedure addenda require a version and declared status')
            item['identity'] = identity
        ledger = _file(root, ledger_path)
        sources = [_file(root, source) for source in source_paths]
        if len({source["path"] for source in sources}) != len(sources):
            raise ValueError("Duplicate source artifact")
        code = _code(root)
        configuration = _file(root, configuration_path) if configuration_path else None
        if configuration:
            configuration['contents'] = json.loads(Path(configuration['path']).read_text(encoding='utf-8'))
        commit = None
        if mode == "live":
            if Path(__file__).resolve() != root / "src" / "run_binding.py":
                raise ValueError("Live binding must identify the checkout containing this runtime")
            if not configuration or not sources:
                raise ValueError("Live run requires a committed configuration and source artifacts")
            if Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
                raise ValueError("Repository root must be the Git checkout root")
            commit = _git(root, "rev-parse", "HEAD")
            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
                raise ValueError("Invalid Git commit")
            if expected_commit is not None and expected_commit != commit:
                raise ValueError("Repository commit differs from requested commit")
            if _git(root, "status", "--porcelain", "--untracked-files=no"):
                raise ValueError("Commit tracked changes before live execution")
            for item in code + [configuration, procedure] + addenda:
                relative = _label(root, item["path"])
                if Path(relative).is_absolute():
                    raise ValueError("Procedure, configuration and code must be committed in the repository")
                _git(root, "ls-files", "--error-unmatch", "--", relative)
            expected_configuration = {
                "mode": mode, "procedure": _label(root, procedure["path"]),
                "ledger": _label(root, ledger["path"]),
                "sources": [_label(root, source["path"]) for source in sources],
                "providers": providers, "prompt_templates_sha256": digest(prompt_templates),
            }
            saved_configuration = json.loads(Path(configuration["path"]).read_text(encoding="utf-8"))
            if addenda or 'procedure_addenda' in saved_configuration:
                expected_configuration['procedure_addenda'] = [_label(root, item['path']) for item in addenda]
            if any(saved_configuration.get(key) != value for key, value in expected_configuration.items()):
                raise ValueError("Runtime inputs differ from the committed run configuration")
        elif expected_commit is not None:
            raise ValueError("Fixture bindings cannot claim a repository commit")
        ident = str(uuid.uuid4())
        manifest = {
            "id": ident, "mode": mode, "created_at": _now(),
            "repository": {"root": str(root), "commit": commit, "code_manifest": code},
            "procedure": procedure, "procedure_addenda": addenda, "ledger": ledger, "sources": sources,
            "providers": providers, "prompt_templates": prompt_templates,
            "prompt_templates_sha256": digest(prompt_templates),
            "configuration": configuration,
        }
        _schema(graph.db)
        with graph.db:
            graph.db.execute("INSERT INTO run_binding VALUES(?,?,?)", (ident, canonical(manifest), digest(manifest)))
        return cls(graph, ident)

    @classmethod
    def load(cls, graph, ident):
        binding = cls(graph, ident)
        binding.inspect()
        return binding

    def inspect(self):
        row = self.g.db.execute("SELECT manifest,digest FROM run_binding WHERE id=?", (self.id,)).fetchone()
        if row is None:
            raise KeyError(self.id)
        manifest = json.loads(row[0])
        if manifest.get("id") != self.id or digest(manifest) != row[1]:
            raise ValueError("Corrupt execution binding")
        return manifest

    def verify(self):
        manifest = self.inspect()
        root = Path(manifest["repository"]["root"])
        files = [manifest["procedure"], manifest["ledger"], *manifest["sources"], *manifest.get('procedure_addenda', [])]
        if manifest["configuration"]:
            files.append(manifest["configuration"])
        for item in files:
            if _file(root, item["path"])["sha256"] != item["sha256"]:
                raise ValueError("Bound input changed: " + _label(root, item["path"]))
        if _code(root) != manifest["repository"]["code_manifest"]:
            raise ValueError("Bound source code changed")
        if manifest["mode"] == "live":
            if Path(__file__).resolve() != root / "src" / "run_binding.py":
                raise ValueError("Loaded runtime differs from the bound checkout")
            if _git(root, "rev-parse", "HEAD") != manifest["repository"]["commit"]:
                raise ValueError("Bound repository commit changed")
            if _git(root, "status", "--porcelain", "--untracked-files=no"):
                raise ValueError("Tracked repository files changed")
        return manifest


class ProviderJournal:
    """Append-only evidence of attempts; Execution remains the lifecycle owner."""
    def __init__(self, graph, binding, provider_role):
        if binding.g is not graph:
            raise ValueError("Binding and journal must use the same graph")
        self.g = graph
        self.binding = binding
        self.provider_role = provider_role
        if provider_role not in binding.inspect()["providers"]:
            raise ValueError("Provider role is absent from the run binding")

    def begin(self, operation, configuration, templates, request):
        ident = str(uuid.uuid4())
        with self.g.db:
            self.g.db.execute("INSERT INTO provider_invocation VALUES(?,?,?,?,?,?)", (
                ident, self.binding.id, self.provider_role, operation, request, _now()))
        self.event(ident, "prepared", {"input_references": {"binding": self.binding.id}})
        try:
            manifest = self.binding.verify()
            if manifest["providers"][self.provider_role] != configuration:
                raise ValueError("Provider configuration differs from the run binding")
            if manifest["prompt_templates"] != templates:
                raise ValueError("Prompt templates differ from the run binding")
        except Exception as exc:
            self.event(ident, "rejected", {"error_type": type(exc).__name__, "reason": "Run binding verification failed"})
            raise
        return ident

    def event(self, invocation, state, detail):
        with self.g.db:
            self.g.db.execute("INSERT INTO provider_event(invocation,state,detail,created_at) VALUES(?,?,?,?)", (
                invocation, state, canonical(detail), _now()))

    def response(self, invocation, value, credential):
        if contains_credential(value, credential):
            self.event(invocation, "response_rejected", {"reason": "Provider echoed a credential; response omitted"})
            raise ValueError("Provider response contained a credential")
        if isinstance(value, bytes):
            # Retain exact transport bytes, including malformed JSON.
            detail = {"format": "base64", "body": base64.b64encode(value).decode("ascii")}
        else:
            detail = {"format": "text" if isinstance(value, str) else "json", "body": value}
        self.event(invocation, "response_received", detail)

    def inspect(self):
        result = []
        for ident, operation, request, created in self.g.db.execute(
                "SELECT id,operation,request,created_at FROM provider_invocation WHERE binding=? AND provider_role=? ORDER BY rowid",
                (self.binding.id, self.provider_role)):
            events = [dict(sequence=sequence, state=state, detail=json.loads(detail), created_at=at)
                      for sequence, state, detail, at in self.g.db.execute(
                          "SELECT sequence,state,detail,created_at FROM provider_event WHERE invocation=? ORDER BY sequence", (ident,))]
            result.append({"id": ident, "operation": operation, "request": request,
                           "created_at": created, "events": events,
                           "state": events[-1]["state"] if events else "prepared"})
        return result
