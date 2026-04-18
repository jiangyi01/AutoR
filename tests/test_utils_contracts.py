from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from src.utils import (
    STAGES,
    build_run_paths,
    canonicalize_stage_markdown,
    ensure_run_config,
    ensure_run_layout,
    initialize_memory,
    load_run_config,
    mark_stage_execution_started,
    validate_stage_artifacts,
    validate_stage_markdown,
    write_text,
)


class UtilsContractTests(unittest.TestCase):
    def _build_paths(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        run_root = Path(tmp_dir.name) / "run"
        paths = build_run_paths(run_root)
        ensure_run_layout(paths)
        write_text(paths.user_input, "contract test")
        initialize_memory(paths, "contract test")
        ensure_run_config(paths, model="sonnet", venue="neurips_2025")
        return paths

    def test_stage_markdown_requires_exact_title_options_and_existing_files(self) -> None:
        paths = self._build_paths()
        stage = STAGES[0]
        markdown = (
            "# Stage 99: Wrong Stage\n\n"
            "## Objective\nok\n\n"
            "## Previously Approved Stage Summaries\nNone yet.\n\n"
            "## What I Did\nok\n\n"
            "## Key Results\nok\n\n"
            "## Files Produced\n- `workspace/notes/missing.md`\n\n"
            "## Suggestions for Refinement\n"
            "1. a\n2. b\n3. c\n4. d\n\n"
            "## Your Options\n"
            "1. something else\n2. x\n3. y\n4. z\n5. q\n6. w\n7. extra\n"
        )

        problems = validate_stage_markdown(markdown, stage=stage, paths=paths)

        self.assertTrue(any("title must be exactly" in problem for problem in problems))
        self.assertTrue(any("Suggestions for Refinement" in problem for problem in problems))
        self.assertTrue(any("Your Options" in problem for problem in problems))
        self.assertTrue(any("missing file" in problem for problem in problems))

    def test_ensure_run_config_preserves_created_at(self) -> None:
        paths = self._build_paths()
        first = load_run_config(paths)
        time.sleep(1)
        ensure_run_config(paths, model="sonnet", venue="neurips_2025")
        second = load_run_config(paths)

        self.assertEqual(first["created_at"], second["created_at"])
        self.assertEqual(second["operator"], "claude")

    def test_stage3_validation_requires_current_execution_data(self) -> None:
        paths = self._build_paths()
        stage = STAGES[2]
        write_text(paths.data_dir / "stale_design.json", '{"stale": true}')
        time.sleep(1)
        mark_stage_execution_started(paths, stage)

        problems = validate_stage_artifacts(stage, paths)

        self.assertTrue(any("current stage execution" in problem for problem in problems))

    def test_canonicalize_stage_markdown_restores_decision_ledger_and_valid_files(self) -> None:
        paths = self._build_paths()
        stage = STAGES[0]
        draft_rel = f"stages/{stage.slug}.tmp.md"
        normalized = canonicalize_stage_markdown(
            stage=stage,
            memory_text=paths.memory.read_text(encoding="utf-8"),
            markdown="",
            fallback_text="incomplete draft output",
            stage_output_path=draft_rel,
        )
        write_text(paths.stage_tmp_file(stage), normalized)

        problems = validate_stage_markdown(normalized, stage=stage, paths=paths)

        self.assertEqual(problems, [])
        self.assertIn("## Decision Ledger", normalized)
        self.assertIn(draft_rel, normalized)


if __name__ == "__main__":
    unittest.main()
