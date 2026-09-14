#!/usr/bin/env python3
"""Prepare agent-run evals and summarize evidence. Does not invoke a model."""
import argparse
import hashlib
import json
import math
import re
import shutil
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(root):
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            h.update(str(path.relative_to(root)).encode() + b"\0")
            h.update(path.read_bytes())
    return h.hexdigest()


def check_skill(root):
    require((root / "SKILL.md").is_file(), f"Missing SKILL.md: {root}")
    for path in root.rglob("*"):
        if ".git" in path.relative_to(root).parts or "__pycache__" in path.parts:
            continue
        require(not path.is_symlink(), f"Snapshot requires regular files, found symlink: {path}")


def prepare(args):
    skill = Path(args.skill).resolve()
    check_skill(skill)
    old = Path(args.baseline_skill).resolve() if args.baseline_skill else None
    if old:
        check_skill(old)
    suite_path = Path(args.evals).resolve() if args.evals else skill / "evals/evals.json"
    suite = read(suite_path)
    require(isinstance(suite, dict) and isinstance(suite.get("skill_name"), str)
            and suite["skill_name"].strip(), "skill_name must be a nonempty string")
    require(isinstance(suite.get("evals"), list) and suite["evals"], "evals must be a nonempty list")
    ids = set()
    cases = []
    for case in suite["evals"]:
        require(isinstance(case, dict), "Each eval must be an object")
        value = case.get("id")
        require((type(value) is int and value > 0) or
                (isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]+", value)), "Invalid eval id")
        cid = str(value)
        require(cid not in ids, f"Duplicate eval id: {cid}")
        ids.add(cid)
        for key in ("prompt", "expected_output"):
            require(isinstance(case.get(key), str) and case[key].strip(), f"eval {cid}: missing {key}")
        assertions = case.get("assertions", [])
        require(isinstance(assertions, list) and all(isinstance(a, str) and a.strip() for a in assertions),
                f"eval {cid}: assertions must be nonempty strings; explicitly adapt other schemas")
        require(len(assertions) == len(set(assertions)), f"eval {cid}: duplicate assertions")
        if args.ids and cid not in args.ids:
            continue
        files = case.get("files", [])
        require(isinstance(files, list), f"eval {cid}: files must be a list")
        resolved = []
        for filename in files:
            require(isinstance(filename, str) and filename.strip(), f"eval {cid}: invalid file path")
            rel = Path(filename)
            require(not rel.is_absolute() and ".." not in rel.parts, f"Import external fixture first: {filename}")
            source = (skill / rel).resolve()
            require(source.is_relative_to(skill) and source.is_file(), f"Missing or escaping fixture: {filename}")
            resolved.append((filename, source))
        cases.append((case, resolved))
    require(not args.ids or set(args.ids) <= ids, "Requested eval id not found")
    require(args.repeat > 0, "repeat must be positive")
    workspace = Path(args.workspace).resolve() if args.workspace else skill.with_name(skill.name + "-workspace")
    require(not workspace.is_relative_to(skill) and (not old or not workspace.is_relative_to(old)),
            "Workspace must be outside source skills")
    workspace.mkdir(parents=True, exist_ok=True)
    number = 1
    while True:
        iteration = workspace / f"iteration-{number}"
        try:
            iteration.mkdir()
            break
        except FileExistsError:
            number += 1
    configs = {"with_skill": skill}
    if not args.candidate_only:
        configs["old_skill" if old else "without_skill"] = old
    snapshots = {}
    for config, source in configs.items():
        if source:
            target = iteration / "snapshots" / config
            shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            snapshots[config] = {"path": str(target), "sha256": digest(target)}
    write(iteration / "evals.json", suite)
    runs = []
    for case, files in cases:
        for config in configs:
            for repetition in range(1, args.repeat + 1):
                relative = f"eval-{case['id']}/{config}/run-{repetition}"
                run_dir = iteration / relative
                (run_dir / "outputs").mkdir(parents=True)
                (run_dir / "inputs").mkdir()
                mapping = {}
                for filename, source in files:
                    dest = run_dir / "inputs" / filename
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
                    mapping[filename] = str(dest)
                task = {"prompt": case["prompt"], "skill_path": snapshots.get(config, {}).get("path"),
                        "input_map": mapping, "output_dir": str(run_dir / "outputs")}
                write(run_dir / "task.json", task)
                write(run_dir / "run.json", {"status": "pending", "environment": {}, "limitations": [], "error": None})
                runs.append({"case_id": str(case["id"]), "config": config, "repeat": repetition,
                             "path": relative, "assertions": case.get("assertions", [])})
    write(iteration / "manifest.json", {"schema_version": 1, "skill_name": suite["skill_name"],
          "configs": list(configs), "snapshots": snapshots,
          "evals_sha256": hashlib.sha256((iteration / "evals.json").read_bytes()).hexdigest(), "runs": runs})
    return {"iteration": str(iteration), "planned_runs": len(runs), "executed_runs": 0}


def metric(value, name):
    require(value is None or (type(value) in (int, float) and math.isfinite(value) and value >= 0
                             and (name != "total_tokens" or type(value) is int)), f"Invalid {name}")
    return value


def stats(values):
    return {"n": len(values), "mean": statistics.mean(values) if values else None}


def collect(iteration, item):
    root = (iteration / item["path"]).resolve()
    require(root.is_relative_to(iteration), "Run path escapes iteration")
    record = {**item, "status": "invalid", "grade": None, "total_tokens": None,
              "duration_ms": None, "errors": [], "environment": {}, "limitations": []}
    try:
        run = read(root / "run.json")
        require(isinstance(run, dict), "run.json must be an object")
        status = run.get("status")
        require(status in ("pending", "completed", "failed", "blocked"), "Invalid run status")
        record.update(status=status, environment=run.get("environment", {}), limitations=run.get("limitations", []),
                      error=run.get("error"))
        require(isinstance(record["environment"], dict) and isinstance(record["limitations"], list),
                "Invalid environment or limitations")
        if (root / "timing.json").exists():
            timing = read(root / "timing.json")
            require(isinstance(timing, dict), "timing.json must be an object")
            for name in ("total_tokens", "duration_ms"):
                record[name] = metric(timing.get(name), name)
        if status != "completed":
            return record
        require((root / "outputs").is_dir() and any(p.is_file() for p in (root / "outputs").rglob("*")),
                "Completed run has no actual output files")
        require((root / "transcript.md").is_file() or (root / "transcript.jsonl").is_file(),
                "Completed run lacks transcript.md or transcript.jsonl")
        assertions = item["assertions"]
        if not assertions or not (root / "grading.json").exists():
            return record
        grading = read(root / "grading.json")
        require(isinstance(grading, dict), "grading.json must be an object")
        results = grading.get("assertion_results")
        require(isinstance(results, list) and all(isinstance(r, dict) for r in results), "Invalid assertion_results")
        require([r.get("text") for r in results] == assertions, "Grading must match frozen assertions in order")
        for result in results:
            require(type(result.get("passed")) is bool or ("passed" in result and result["passed"] is None),
                    "passed must be true, false or null")
            require(isinstance(result.get("evidence"), str) and result["evidence"].strip(), "Missing assertion evidence")
        counts = {"passed": sum(r["passed"] is True for r in results),
                  "failed": sum(r["passed"] is False for r in results),
                  "unresolved": sum(r["passed"] is None for r in results), "total": len(results)}
        counts["pass_rate"] = counts["passed"] / counts["total"] if counts["unresolved"] == 0 else None
        record["grade"] = counts
    except (ValueError, OSError, TypeError, KeyError) as exc:
        record["errors"].append(str(exc))
    return record


def comparable(a, b):
    for record in (a, b):
        env = record["environment"]
        if (record["errors"] or record["status"] != "completed" or not record["grade"]
                or record["grade"]["pass_rate"] is None or record["limitations"]
                or env.get("isolation") != "verified" or not env.get("isolation_evidence")):
            return False
        if not all(env.get(k) for k in ("model", "settings", "comparison_key")) or "tools" not in env:
            return False
    return all(a["environment"].get(k) == b["environment"].get(k)
               for k in ("model", "settings", "tools", "comparison_key"))


def summarize(args):
    iteration = Path(args.iteration).resolve()
    manifest = read(iteration / "manifest.json")
    errors = []
    for config, snap in manifest["snapshots"].items():
        path = Path(snap["path"])
        if not path.is_dir() or digest(path) != snap["sha256"]:
            errors.append(f"Snapshot changed or missing: {config}")
    if hashlib.sha256((iteration / "evals.json").read_bytes()).hexdigest() != manifest["evals_sha256"]:
        errors.append("Frozen evals.json changed")
    records = [collect(iteration, item) for item in manifest["runs"]]
    groups = {}
    per_case = defaultdict(list)
    for config in manifest["configs"]:
        group = [r for r in records if r["config"] == config]
        graded = [r for r in group if not r["errors"] and r["grade"] and r["grade"]["pass_rate"] is not None]
        passed = sum(r["grade"]["passed"] for r in graded)
        total = sum(r["grade"]["total"] for r in graded)
        groups[config] = {"status_counts": dict(Counter(r["status"] for r in group)),
                          "planned": len(group), "graded": len(graded),
                          "ungraded_completed": sum(r["status"] == "completed" for r in group) - len(graded),
                          "invalid_records": sum(bool(r["errors"]) for r in group),
                          "passed": passed, "total": total, "pass_rate": passed / total if total else None,
                          "tokens": stats([r["total_tokens"] for r in group if r["total_tokens"] is not None]),
                          "time_seconds": stats([r["duration_ms"] / 1000 for r in group if r["duration_ms"] is not None])}
        for r in graded:
            per_case[(r["case_id"], config)].append(r["grade"]["pass_rate"])
    by_key = {(r["case_id"], r["repeat"], r["config"]): r for r in records}
    baseline = next((c for c in manifest["configs"] if c != "with_skill"), None)
    pairs = []
    if baseline and not errors:
        for a in records:
            if a["config"] == "with_skill":
                b = by_key.get((a["case_id"], a["repeat"], baseline))
                if b and comparable(a, b):
                    pairs.append((a, b))
    delta = None
    if pairs:
        rates = [sum(p[i]["grade"]["passed"] for p in pairs) / sum(p[i]["grade"]["total"] for p in pairs)
                 for i in (0, 1)]
        delta = {"paired_runs": len(pairs), "with_skill_pass_rate": rates[0],
                 "baseline_pass_rate": rates[1], "pass_rate": rates[0] - rates[1]}
        for name, scale in (("total_tokens", 1), ("duration_ms", 1000)):
            values = [(a[name] - b[name]) / scale for a, b in pairs if a[name] is not None and b[name] is not None]
            delta["tokens" if name == "total_tokens" else "time_seconds"] = stats(values)
    variability = [{"case_id": cid, "config": config, **stats(values),
                    "stddev": statistics.stdev(values) if len(values) > 1 else None}
                   for (cid, config), values in sorted(per_case.items())]
    result = {"schema_version": 1, "planned_runs": len(records), "run_summary": groups,
              "paired_runs": len(pairs), "delta": delta, "per_case_variability": variability,
              "errors": errors, "runs": records,
              "human_review": "See feedback.json; absence means not_reviewed"}
    write(iteration / "benchmark.json", result)
    lines = ["# Skill eval 执行报告", "", "这是实际收集结果的摘要；准备任务不等于运行完成。", "",
             "| 配置 | 计划 | 状态数量 | 完整评分 | 断言通过 |", "|---|---:|---|---:|---:|"]
    for config, group in groups.items():
        score = f"{group['passed']}/{group['total']}" if group["total"] else "未评分"
        lines.append(f"| {config} | {group['planned']} | {json.dumps(group['status_counts'])} | {group['graded']} | {score} |")
    lines += ["", f"可比配对：{len(pairs)}。"]
    lines.append(f"配对通过率差值：{delta['pass_rate'] * 100:.2f} 个百分点。" if delta else "没有足够的可比评分，不计算技能收益。")
    if delta:
        for name in ("tokens", "time_seconds"):
            lines.append(f"{name} 平均差值：{delta[name]['mean']}；有效配对数：{delta[name]['n']}。")
    lines += ["", "## 运行与证据", ""]
    for r in records:
        lines.append(f"- [{r['path']}]({r['path']}/run.json)：{r['status']}；"
                     f"[产物]({r['path']}/outputs/)；[评分]({r['path']}/grading.json)；[日志]({r['path']}/transcript.md)")
        if r["errors"] or r.get("error") or r["limitations"]:
            lines.append("  " + json.dumps({"errors": r["errors"], "error": r.get("error"),
                                           "limitations": r["limitations"]}, ensure_ascii=False))
    lines += ["", "人工评审：未收到反馈时为 not_reviewed。小样本结果仅供本轮观察。", ""]
    lines += ["错误：" + error for error in errors]
    (iteration / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"benchmark": str(iteration / "benchmark.json"), "report": str(iteration / "report.md"),
            "planned_runs": len(records), "paired_runs": len(pairs), "errors": errors,
            "invalid_records": sum(bool(r["errors"]) for r in records)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="Prepare frozen inputs; does not invoke a model")
    prep.add_argument("--skill", required=True)
    prep.add_argument("--evals")
    prep.add_argument("--workspace")
    prep.add_argument("--ids", nargs="+")
    prep.add_argument("--repeat", type=int, default=1)
    mode = prep.add_mutually_exclusive_group()
    mode.add_argument("--baseline-skill")
    mode.add_argument("--candidate-only", action="store_true")
    summary = sub.add_parser("summarize")
    summary.add_argument("iteration")
    args = parser.parse_args()
    try:
        result = prepare(args) if args.command == "prepare" else summarize(args)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("errors") or result.get("invalid_records"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
