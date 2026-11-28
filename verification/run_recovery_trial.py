"""Drive one bound recovery experiment through the existing Execution owner.

This command does not author prose, invent an alternate lifecycle, or approve
the final result. It applies the author's recorded delegation to the existing
construction-closure and local-repair commands, and stops at a detector result
or an unresolved state. Every model request remains in ProviderJournal.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model import Graph
from ingest import ingest
from run_agent import create_binding, inspect_execution, read_configuration, runtime
from run_binding import RunBinding


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)


def select_execution(rows, execution_id=None):
    executions = [json.loads(row[0]) for row in rows]
    if execution_id is not None:
        matches = [item for item in executions if item['id'] == execution_id]
        if len(matches) != 1:
            raise ValueError('The requested execution ID is not present in this trial database')
        return matches[0]
    if len(executions) > 1:
        raise ValueError('Select --execution explicitly when a database retains parent executions')
    return executions[0] if executions else None


def driver_step_limit(config, act_count):
    """Operational ceiling including polling; never a replacement writing budget."""
    groups = config.get('paragraph_groups')
    paragraphs = 1 if groups == 'all_acts_one_paragraph' else len(groups) if isinstance(groups, list) else max(1, act_count)
    # Allow roughly thirty async polls per candidate, plus owner transitions.
    return 16 + 3 * config.get('max_voice_repairs', 0) + 32 * config.get('max_attempts', 3) * paragraphs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execution", help="Exact execution ID, required for a continuation database")
    args = parser.parse_args()
    config = read_configuration(args.config)
    delegation = config.get("recovery_authorization", {})
    if delegation.get("construction_closure_and_local_repairs") is not True:
        raise ValueError("Recorded author delegation is required")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    graph = Graph(str(out / "run.sqlite"))
    try:
        rows = graph.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='execution'").fetchall()
        executions = graph.db.execute("SELECT data FROM execution").fetchall() if rows else []
        current = select_execution(executions, args.execution)
        if current is not None:
            binding = RunBinding.load(graph, current["binding_id"])
            engine, _, _ = runtime(graph, binding, config)
            current = engine.inspect(current["id"])
        else:
            if config.get('continuation') is not None:
                raise ValueError('Prepare the imported continuation through run_agent continue-expression first')
            binding, config = create_binding(graph, args.config, repository_root=ROOT)
            ingest(graph, binding.inspect()["ledger"]["path"])
            engine, _, _ = runtime(graph, binding, config)
            print(json.dumps({"experiment": config["id"], "stage": "construction_started"}), flush=True)
            current = engine.start(config["intent"], max_attempts=config["max_attempts"], mode="live")
        seen_revisions = {int(p.stem.split("-")[-1]) for p in out.glob("checkpoint-*.json")}
        plan = graph.db.execute('SELECT acts FROM construction_plan WHERE id=?',
                                (current.get('plan'),)).fetchone()
        step_limit = driver_step_limit(config, len(json.loads(plan[0])) if plan else 1)
        steps, limit_reached = 0, False
        for step in range(step_limit):
            steps = step + 1
            report = inspect_execution(graph, current["id"])
            revision = current["revision"]
            if revision not in seen_revisions:
                save(out / f"checkpoint-{revision:03d}.json", report)
                seen_revisions.add(revision)
            brief = {"experiment": config["id"], "execution": current["id"],
                     "state": current["state"], "revision": revision,
                     "attempts": current.get("attempts", 0),
                     "voice_repairs": current.get("voice_repair_attempts", 0)}
            if report.get("construction_review"):
                brief["construction_checks"] = {x["layer"]: x["status"] for x in report["construction_review"]["findings"]}
            if report.get("assessment"):
                brief["paragraph_checks"] = {x["layer"]: x["status"] for x in report["assessment"]["findings"]}
            print(json.dumps(brief), flush=True)
            state = current["state"]
            if state == "awaiting_construction_closure":
                save(out / f"delegated-closure-{revision:03d}.json", {
                    "execution": current["id"], "plan": current["plan"],
                    "review": current["construction_review"], "authorization": delegation,
                    "scope": "Operational construction closure after passing review; final author approval remains pending.",
                })
                current = engine.close_construction(current["id"], actor="author")
            elif state in {"awaiting_construction_review", "construction_review_required"}:
                if state == "awaiting_construction_review":
                    current = engine.review_construction(current["id"])
                else:
                    statuses = brief.get("construction_checks")
                    if (statuses != {"conceptual": "pass", "epistemic": "pass", "rhetorical_plan": "fail"}
                            or current.get("route") == "construction"
                            or current.get("voice_repair_attempts", 0) >= config.get("max_voice_repairs", 0)):
                        break
                    current = engine.repair_voice(current["id"], actor="author")
            elif state in {"ready", "ready_for_next_paragraph", "suspended_detector_pending"}:
                if state == "suspended_detector_pending":
                    time.sleep(2)
                current = engine.advance(current["id"])
            elif state == "suspended_reopen" and current.get("route") == "expression":
                current = engine.advance(current["id"], actor="author")
            elif state == "suspended_detector_flagged":
                if (not config.get('fresh_expression_retry')
                        or delegation.get('fresh_expression_after_detector_flag') is not True):
                    break
                current = engine.retry_fresh_expression(current['id'], actor='author')
            elif state == 'ready_for_fresh_expression':
                if delegation.get('fresh_expression_after_detector_flag') is not True:
                    break
                current = engine.advance(current['id'], actor='author')
            else:
                break
        else:
            limit_reached = True
        final = inspect_execution(graph, current["id"])
        final['driver'] = {
            'step_limit': step_limit, 'steps': steps,
            'stop_reason': 'driver_step_limit_reached' if limit_reached else 'owner_or_authorization_gate',
            'resume_execution': current['id'] if limit_reached else None,
            'scope': 'Operational polling/transition ceiling only. Resume this exact execution and database; committed writing and fresh-retry budgets do not reset.',
        }
        result_name = "result-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
        save(out / result_name, final)
        print(json.dumps({"result_file": str(out / result_name), "state": current["state"],
                          'driver_stop_reason': final['driver']['stop_reason'],
                          'resume_execution': final['driver']['resume_execution']}), flush=True)
    finally:
        graph.db.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never print a transport exception or credential-bearing environment.
        print(json.dumps({"state": "driver_error", "error_type": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1)
