"""Optional, user-confirmed quality rubric; independent of boolean assertions."""
import math


def text(value):
    return isinstance(value, str) and bool(value.strip())


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_scoring(rubric, *, confirmed=False):
    errors = []
    if not isinstance(rubric, dict):
        return ["scoring must be an object"]
    if rubric.get("status") not in ("proposed", "confirmed"):
        errors.append("scoring.status must be proposed or confirmed")
    if confirmed and rubric.get("status") != "confirmed":
        errors.append("scoring requires user confirmation before prepare")
    if rubric.get("status") == "confirmed" and not text(rubric.get("confirmation")):
        errors.append("confirmed scoring requires a confirmation reference")
    dimensions = rubric.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        return errors + ["scoring.dimensions must be a nonempty array"]
    ids, weights = set(), []
    for index, dimension in enumerate(dimensions):
        label = f"scoring.dimensions[{index}]"
        if not isinstance(dimension, dict):
            errors.append(f"{label}: must be an object")
            continue
        did = dimension.get("id")
        if not text(did):
            errors.append(f"{label}: id must be nonempty text")
        elif did in ids:
            errors.append(f"{label}: duplicate dimension id {did}")
        else:
            ids.add(did)
        if not text(dimension.get("description")):
            errors.append(f"{label}: description must be nonempty text")
        weight = dimension.get("weight_percent")
        if not number(weight) or not 0 < weight <= 100:
            errors.append(f"{label}: weight_percent must be in (0, 100]")
        else:
            weights.append(weight)
        anchors = dimension.get("anchors")
        if not isinstance(anchors, dict) or not all(text(anchors.get(key)) for key in ("0", "3", "5")):
            errors.append(f"{label}: anchors must describe scores 0, 3 and 5")
    if len(weights) == len(dimensions) and not math.isclose(sum(weights), 100, rel_tol=0, abs_tol=1e-6):
        errors.append("scoring weights must sum to 100 percent")
    return errors


def score_results(rubric, results):
    errors = validate_scoring(rubric, confirmed=True)
    if errors:
        raise ValueError("; ".join(errors))
    dimensions = rubric["dimensions"]
    if (not isinstance(results, list) or not all(isinstance(r, dict) for r in results)
            or [r.get("id") for r in results] != [d["id"] for d in dimensions]):
        raise ValueError("score_results must match frozen dimensions in order")
    items = []
    for dimension, result in zip(dimensions, results):
        value = result.get("score")
        if "score" not in result or (value is not None and (not number(value) or not 0 <= value <= 5)):
            raise ValueError("score must be a finite number from 0 to 5 or explicit null")
        if not text(result.get("evidence")):
            raise ValueError("Missing score evidence")
        contribution = value / 5 * dimension["weight_percent"] if value is not None else None
        items.append({"id": dimension["id"], "score": value, "weight_percent": dimension["weight_percent"],
                      "contribution": contribution, "evidence": result["evidence"]})
    unresolved = sum(item["score"] is None for item in items)
    return {"total": sum(item["contribution"] for item in items) if not unresolved else None,
            "out_of": 100, "unresolved": unresolved, "dimensions": items}
