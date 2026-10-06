#!/usr/bin/env python3
"""Read-only checks for the local evals contract; not a model grader."""

import argparse
import json
from pathlib import Path


def nonempty_text(value):
    return isinstance(value, str) and bool(value.strip())


def validate(path, root):
    errors = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        return [f"Cannot read JSON: {exc}"]
    if not isinstance(data, dict):
        return ["Top level must be an object"]
    if not nonempty_text(data.get("skill_name")):
        errors.append("skill_name must be nonempty text")
    cases = data.get("evals")
    if not isinstance(cases, list) or not cases:
        return errors + ["evals must be a nonempty array"]
    seen = set()
    root = root.resolve()
    for index, case in enumerate(cases):
        label = f"evals[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{label}: must be an object")
            continue
        case_id = case.get("id")
        if type(case_id) is not int or case_id <= 0:
            errors.append(f"{label}: id must be a positive integer")
        elif case_id in seen:
            errors.append(f"{label}: duplicate id {case_id}")
        else:
            seen.add(case_id)
        for field in ("prompt", "expected_output"):
            if not nonempty_text(case.get(field)):
                errors.append(f"{label}: {field} must be nonempty text")
        for field in ("files", "assertions"):
            if field not in case:
                continue
            values = case[field]
            if not isinstance(values, list) or not all(nonempty_text(v) for v in values):
                errors.append(f"{label}: {field} must be an array of nonempty strings")
                continue
            if field == "assertions" and not values:
                errors.append(f"{label}: omit assertions until checks are available")
            if field != "files":
                continue
            for value in values:
                relative = Path(value)
                if relative.is_absolute() or ".." in relative.parts:
                    errors.append(f"{label}: file must be relative to skill root: {value}")
                    continue
                try:
                    target = (root / relative).resolve()
                    target.relative_to(root)
                    if not target.is_file():
                        errors.append(f"{label}: input file missing or not a file: {value}")
                except (OSError, RuntimeError, ValueError):
                    errors.append(f"{label}: invalid file path or resolves outside skill root: {value}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evals_json", type=Path)
    parser.add_argument("--skill-root", type=Path, help="Defaults to evals.json parent.parent")
    args = parser.parse_args()
    root = args.skill_root or args.evals_json.resolve().parent.parent
    errors = validate(args.evals_json, root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("PASS: eval structure and listed input files; model behavior not evaluated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
