from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.manager import ResearchManager
from src.operator import ClaudeOperator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AutoR research workflow runner")
    parser.add_argument(
        "--goal",
        help="Research goal. If omitted, the goal is collected from terminal input.",
    )
    parser.add_argument(
        "--runs-dir",
        default="runs",
        help="Directory used to store run artifacts. Defaults to runs/ under the repo root.",
    )
    parser.add_argument(
        "--fake-operator",
        action="store_true",
        help="Use a fake operator for local validation instead of invoking Claude.",
    )
    parser.add_argument(
        "--model",
        default="sonnet",
        help="Claude model alias or full model name for real runs. Defaults to 'sonnet'.",
    )
    return parser.parse_args()


def read_user_goal() -> str:
    print("Enter your research goal. Finish with an empty line on a new line:")
    lines: list[str] = []

    while True:
        prompt = "> " if not lines else ""
        try:
            line = input(prompt)
        except EOFError:
            break

        if not line.strip():
            if lines:
                break
            continue

        lines.append(line.rstrip())

    goal = "\n".join(lines).strip()
    if not goal:
        raise ValueError("Research goal cannot be empty.")
    return goal


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent
    goal = args.goal.strip() if args.goal else read_user_goal()

    operator = ClaudeOperator(model=args.model, fake_mode=args.fake_operator)
    manager = ResearchManager(
        project_root=repo_root,
        runs_dir=repo_root / args.runs_dir,
        operator=operator,
    )
    manager.run(goal)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
