"""Validate the evaluator's detection of Correct-But-Unjustified (CBU) samples.

This script reads the synthetic CBU injection dataset, runs each sample through
`ProcessEvaluator` with the GPT judge configured via `.env`, and reports how
often the evaluator flags `correct_but_unjustified`.
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Make project root importable
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env before any module that reads environment variables
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_PATH, override=False)
    except ImportError:
        pass

from app.hy3_client import load_judge_client_from_env  # noqa: E402
from evaluator.error_classifier import normalize_error_type  # noqa: E402
from evaluator.llm_judge import LLMJudge  # noqa: E402
from evaluator.process_evaluator import ProcessEvaluator, evaluate_record  # noqa: E402

# Expected error mechanism for each synthetic CBU sample.
# Existing records (001-005) are annotated retroactively; new records (006-009)
# are designed to exercise calculation errors, skipped steps, hallucinations,
# and circular reasoning respectively.
EXPECTED_ERROR_TYPE = {
    "CBU-INJ-001": "定理/公式误用",
    "CBU-INJ-002": "定理/公式误用",
    "CBU-INJ-003": "计算错误",
    "CBU-INJ-004": "概念理解错误",
    "CBU-INJ-005": "定理/公式误用",
    "CBU-INJ-006": "计算错误",
    "CBU-INJ-007": "跳步推导",
    "CBU-INJ-008": "幻觉/无中生有",
    "CBU-INJ-009": "循环论证",
}


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load a JSONL file."""
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def reconstruct_raw_output(steps: List[Dict[str, Any]]) -> str:
    """Build a non-empty raw output string from step texts.

    The synthetic CBU samples store `raw_output` as `""`. Passing an empty
    `raw_output` to `ProcessEvaluator` triggers a false "output empty"
    truncation flag that masks the real first error step. Reconstructing the
    text from the steps avoids that artifact while preserving the step content.
    """
    lines = []
    for i, step in enumerate(steps):
        idx = step.get("index", i + 1)
        text = step.get("text", "")
        lines.append(f"步骤 {idx}: {text}")
    return "\n".join(lines)


def evaluate_with_retry(
    record: Dict[str, Any], evaluator: ProcessEvaluator, max_retries: int = 1
) -> Tuple[Dict[str, Any], bool]:
    """Evaluate a single record, retrying once on failure.

    Returns:
        (evaluation_dict, success)
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            ev = evaluate_record(record, evaluator, use_llm=True)
            return ev, True
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                print(f"  [{record.get('problem_id')}] evaluation failed ({e}); retrying...")
                time.sleep(2.0)

    error_ev = {
        "problem_id": record.get("problem_id"),
        "level": record.get("level"),
        "answer_correct": record.get("answer_correct"),
        "gold_answer": record.get("gold_answer"),
        "final_answer": record.get("final_answer"),
        "process_correct": None,
        "first_error_step": None,
        "error_type": "其他/无法归类",
        "error_detail": f"Evaluation failed after {max_retries} retries: {last_error}",
        "correct_but_unjustified": {"correct_but_unjustified": False, "reason": "evaluation error"},
        "evaluation_error": str(last_error),
    }
    return error_ev, False


def build_metrics(evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute CBU detection metrics and per-error-type rates."""
    total = len(evaluations)
    detected = 0
    per_type: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "detected": 0})
    per_expected: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "detected": 0})
    errors = []

    for ev in evaluations:
        pid = ev.get("problem_id", "")
        expected = EXPECTED_ERROR_TYPE.get(pid, "其他/无法归类")
        ev["expected_error_type"] = expected

        cbu = bool(ev.get("correct_but_unjustified", {}).get("correct_but_unjustified"))
        if cbu:
            detected += 1

        err_type = normalize_error_type(ev.get("error_type"))
        per_type[err_type]["total"] += 1
        if cbu:
            per_type[err_type]["detected"] += 1

        per_expected[expected]["total"] += 1
        if cbu:
            per_expected[expected]["detected"] += 1

        if ev.get("evaluation_error"):
            errors.append({"problem_id": pid, "error": ev["evaluation_error"]})

    def _rates(counter: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, Any]]:
        out = {}
        for err_type, counts in sorted(counter.items()):
            out[err_type] = {
                "total": counts["total"],
                "detected": counts["detected"],
                "detection_rate": counts["detected"] / counts["total"] if counts["total"] else 0.0,
            }
        return out

    return {
        "total": total,
        "detected_cbu": detected,
        "missed_cbu": total - detected,
        "detection_rate": detected / total if total else 0.0,
        "per_error_type": _rates(per_type),
        "per_expected_error_type": _rates(per_expected),
        "evaluation_errors": errors,
    }


def build_report(metrics: Dict[str, Any], evaluations: List[Dict[str, Any]]) -> str:
    """Build a Markdown summary report."""
    lines = [
        "# CBU Injection Validation Report",
        "",
        "This report summarizes how well `ProcessEvaluator` detects the synthetic",
        '"Correct But Unjustified" samples in `dataset/cbu_injection_samples.jsonl`.',
        "",
        "## Summary",
        "",
        f"- **Total CBU samples**: {metrics['total']}",
        f"- **Detected as CBU**: {metrics['detected_cbu']}",
        f"- **Missed**: {metrics['missed_cbu']}",
        f"- **CBU detection rate**: {metrics['detection_rate']:.2%}",
        "",
    ]

    if metrics["evaluation_errors"]:
        lines.extend(
            [
                "## Evaluation Errors",
                "",
                "The following samples could not be evaluated (API or runtime failure):",
                "",
            ]
        )
        for err in metrics["evaluation_errors"]:
            lines.append(f"- `{err['problem_id']}`: {err['error']}")
        lines.append("")

    lines.extend(
        [
            "## Per-Expected-Mechanism Detection",
            "",
            "Detection rate grouped by the *intended* CBU mechanism of each sample.",
            "",
        ]
    )
    lines.append("| Expected Mechanism | Total | Detected | Detection Rate |")
    lines.append("|--------------------|------:|---------:|---------------:|")
    for err_type, rates in metrics["per_expected_error_type"].items():
        lines.append(
            f"| {err_type} | {rates['total']} | {rates['detected']} | "
            f"{rates['detection_rate']:.2%} |"
        )
    lines.append("")

    lines.extend(["## Per-Detected-Error-Type Detection", ""])
    lines.append("| Detected Error Type | Total | Detected | Detection Rate |")
    lines.append("|---------------------|------:|---------:|---------------:|")
    for err_type, rates in metrics["per_error_type"].items():
        lines.append(
            f"| {err_type} | {rates['total']} | {rates['detected']} | "
            f"{rates['detection_rate']:.2%} |"
        )
    lines.append("")

    lines.extend(["## Per-Sample Results", ""])
    lines.append(
        "| Problem ID | Level | Expected Mechanism | First Error Step | Assigned Error Type | CBU Detected |"
    )
    lines.append(
        "|------------|------:|--------------------|-----------------:|--------------------:|:------------:|")
    for ev in evaluations:
        pid = ev.get("problem_id", "")
        level = ev.get("level", "")
        expected = ev.get("expected_error_type", "")
        first_err = ev.get("first_error_step")
        first_err_str = str(first_err) if first_err is not None else "N/A"
        err_type = ev.get("error_type", "")
        cbu = "Yes" if ev.get("correct_but_unjustified", {}).get("correct_but_unjustified") else "No"
        lines.append(
            f"| {pid} | {level} | {expected} | {first_err_str} | {err_type} | {cbu} |"
        )
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Validate CBU injection detection")
    parser.add_argument(
        "--input",
        type=str,
        default="dataset/cbu_injection_samples.jsonl",
        help="Path to CBU injection dataset",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="results/validation_cbu_injection.json",
        help="Path to write detailed JSON results",
    )
    parser.add_argument(
        "--output-report",
        type=str,
        default="results/validation_cbu_injection_report.md",
        help="Path to write Markdown summary report",
    )
    args = parser.parse_args()

    input_path = PROJECT_ROOT / args.input
    output_json_path = PROJECT_ROOT / args.output_json
    output_report_path = PROJECT_ROOT / args.output_report

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_report_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading CBU injection dataset: {input_path}")
    records = load_jsonl(input_path)
    print(f"Loaded {len(records)} samples")

    print("Loading GPT judge client...")
    judge_client = load_judge_client_from_env()
    llm_judge = LLMJudge(client=judge_client)
    evaluator = ProcessEvaluator(llm_judge=llm_judge)

    evaluations = []
    for record in records:
        pid = record.get("problem_id", "unknown")
        print(f"Evaluating {pid}...")

        # Avoid the false "output empty" truncation flag on synthetic samples
        if not record.get("raw_output"):
            record["raw_output"] = reconstruct_raw_output(record.get("steps", []))

        ev, success = evaluate_with_retry(record, evaluator, max_retries=1)
        if not success:
            print(f"  [{pid}] FAILED after retry: {ev.get('evaluation_error')}")
        else:
            cbu = ev.get("correct_but_unjustified", {}).get("correct_but_unjustified")
            first_err = ev.get("first_error_step")
            err_type = ev.get("error_type", "")
            print(f"  [{pid}] CBU={cbu}, first_error_step={first_err}, error_type={err_type}")
        evaluations.append(ev)

    metrics = build_metrics(evaluations)

    result = {
        "evaluations": evaluations,
        "metrics": metrics,
    }
    with output_json_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nDetailed results saved to: {output_json_path}")

    report = build_report(metrics, evaluations)
    with output_report_path.open("w", encoding="utf-8") as f:
        f.write(report)
    print(f"Summary report saved to: {output_report_path}")

    print("\n" + "=" * 60)
    print(report)


if __name__ == "__main__":
    main()
