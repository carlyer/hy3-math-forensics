"""合并 L1/L2（3k）与 L3/L4（6k）的生成结果."""

import argparse
import json
from pathlib import Path


def load_jsonl(path: str):
    records = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                records[rec["problem_id"]] = rec
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="results/solutions_merged_depgraph.jsonl")
    parser.add_argument("--override", default="results/solutions_merged_l3l4_6k.jsonl")
    parser.add_argument("--output", default="results/solutions_merged_depgraph_6k.jsonl")
    args = parser.parse_args()

    base = load_jsonl(args.base)
    override = load_jsonl(args.override)

    merged = {**base, **override}
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for rec in merged.values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Base: {len(base)} records from {args.base}")
    print(f"Override: {len(override)} records from {args.override}")
    print(f"Merged: {len(merged)} records -> {args.output}")


if __name__ == "__main__":
    main()
