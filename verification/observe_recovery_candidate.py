"""Observe an exact saved recovery draft without advancing its writing run.

The author explicitly requested iterative Pangram observations. Preserve the
existing four-layer result, even if it has not passed; an observation neither
waives that result nor grants author approval. Reuse the existing HTTP adapter
and detector-result validator, with a private task and no duplicate submission.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.runtime.resolve() / "src"))
    from run_agent import _read_only_graph, inspect_execution
    from pangram_check import PangramCheck, validate_configuration
    from run_binding import canonical, contains_credential

    graph = _read_only_graph(args.run / "run.sqlite")
    try:
        rows = graph.db.execute("SELECT data FROM execution").fetchall()
        if len(rows) != 1:
            raise ValueError("One exact source execution required")
        execution = json.loads(rows[0][0])
        report = inspect_execution(graph, execution["id"])
    finally:
        graph.db.close()
    if report["binding_verification"]["state"] != "current":
        raise ValueError("Source binding is not current")
    draft = report["draft"]
    text = " ".join(item["payload"]["text"].strip() for item in draft["sentences"])
    text_sha = hashlib.sha256(text.encode()).hexdigest()
    if draft.get("text_sha256", text_sha) != text_sha:
        raise ValueError("Source text identity mismatch")
    config = validate_configuration(report["binding"]["configuration"]["contents"]["pangram"])
    if len(text.split()) < config["minimum_words"]:
        raise ValueError("Exact candidate is too short; do not pad it")
    key = os.environ.get(config["key_env"])
    if not key:
        raise ValueError("Pangram credential is unavailable")
    out = args.run / ("observation-" + text_sha[:16])
    out.mkdir(exist_ok=True)
    def save(name, value):
        with (out / name).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
    def now():
        return datetime.now(timezone.utc).isoformat()
    if (out / "result.json").exists():
        print(json.dumps(json.loads((out / "result.json").read_text())["summary"]))
        return
    if not (out / "input.json").exists():
        save("input.json", {"at": now(), "text": text, "text_sha256": text_sha,
            "execution": execution["id"], "run": execution["run"],
            "execution_state": execution["state"], "assessment": report.get("assessment"),
            "configuration": config,
            "authorization": "Author requested iterative code-created candidates and Pangram testing toward 100% human.",
            "scope": "Observation only; original assessment and writing execution remain unchanged."})
    task = None
    requests = sorted(out.glob("request-*.json"))
    for request in requests:
        response = out / ("response-" + request.stem.split("-")[-1] + ".json")
        if not response.exists():
            raise ValueError("Prior request outcome uncertain; do not submit twice")
        response = json.loads(response.read_text())
        if not 200 <= response["http_status"] < 300:
            raise ValueError("Prior response failed; inspect it before any retry")
        task = response["parsed"].get("task_id", task)
        if response["parsed"].get("stage") == "STAGE_SUCCESS":
            raise ValueError("Completed response preserved; do not resubmit")
    validator = object.__new__(PangramCheck)
    validator.configuration = config
    for number in range(len(requests) + 1, len(requests) + 21):
        if task and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", task):
            raise ValueError("Invalid task identifier")
        method = "GET" if task else "POST"
        url = config["endpoint"] + "/task" + ("/" + task if task else "")
        body = None if task else {"text": text, "model": config["model"], "public_dashboard_link": False}
        save(f"request-{number:03d}.json", {"at": now(), "method": method, "url": url, "body": body})
        request = urllib.request.Request(url, data=canonical(body).encode() if body else None,
            headers={"x-api-key": key, "Content-Type": "application/json"}, method=method)
        reply = PangramCheck._http(request)
        if contains_credential(reply.body, key):
            raise ValueError("Echoed credential; response withheld")
        raw = reply.body.decode()
        parsed = json.loads(raw)
        save(f"response-{number:03d}.json", {"at": now(), "http_status": reply.status,
            "raw_response": raw, "parsed": parsed})
        if not 200 <= reply.status < 300:
            raise ValueError("Detector request failed")
        if method == "POST":
            task = parsed.get("task_id")
            if not isinstance(task, str):
                raise ValueError("Missing task identifier")
            print(json.dumps({"state": "submitted", "text_sha256": text_sha}), flush=True)
        elif parsed.get("stage") == "STAGE_SUCCESS":
            if parsed.get("task_id", task) != task:
                raise ValueError("Task identity mismatch")
            policy = PangramCheck._success(validator, parsed, {"text": text})
            summary = {"state": "completed", "policy_result": policy,
                "fraction_human": parsed["fraction_human"], "fraction_ai": parsed["fraction_ai"],
                "fraction_ai_assisted": parsed["fraction_ai_assisted"], "version": parsed["version"],
                "words": len(text.split()), "text_sha256": text_sha,
                "four_layer_state": report.get("assessment", {}).get("state"),
                "source_execution_state": execution["state"]}
            save("result.json", {"at": now(), "summary": summary, "exact_text": text,
                "detector_result": parsed, "source_assessment": report.get("assessment")})
            print(json.dumps(summary), flush=True)
            return
        elif parsed.get("stage") == "STAGE_FAILED":
            raise ValueError("Detector task failed")
        time.sleep(2)
    print(json.dumps({"state": "pending", "task_id": task, "poll_only": True}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"state": "observation_error", "error_type": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1)
