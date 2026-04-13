from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.hypothesis_manifest import load_hypothesis_manifest, write_hypothesis_manifest
from src.manager import ResearchManager
from src.operator import ClaudeOperator
from src.terminal_ui import TerminalUI
from src.utils import (
    STAGES,
    build_hypothesis_context,
    build_run_paths,
    ensure_run_config,
    ensure_run_layout,
    initialize_memory,
    validate_stage_markdown,
    write_stage_handoff,
    write_text,
)


STAGE_02_TYPED = """\
# Stage 02: Hypothesis Generation

## Objective
Generate typed claims from the literature survey.

## Previously Approved Stage Summaries
_None yet._

## What I Did
Converted the literature into typed propositions, hypotheses, and paper claims.

## Key Results

### Theoretical Propositions
- **T1**: Attention bottlenecks cause long-context degradation.
  - Derived from: Prior scaling literature and Stage 01 synthesis.

### Empirical Hypotheses
- **H1**: Adding retrieval augmentation will improve long-context accuracy by at least 8 points.
  - Depends on: T1
  - Verification: Compare retrieval-on vs retrieval-off on the evaluation suite.

### Paper Claims (Provisional)
- **C1**: Retrieval augmentation is a practical fix for long-context reasoning failures.
  - Status: proposed

## Files Produced
- `workspace/notes/hypothesis_manifest.json` - machine-readable typed claim bundle
- `workspace/notes/hypotheses.md` - typed hypothesis notes

## Decision Ledger
- **Open Questions**: Does retrieval increase latency too much?
- **Locked Decisions**: Focus on long-context QA.
- **Assumptions**: The base model remains unchanged.
- **Rejected Alternatives**: Full model retraining.

## Suggestions for Refinement
1. Add a second empirical hypothesis about latency trade-offs.
2. Tighten the expected effect size with prior evidence.
3. Add a fallback paper claim with weaker language.

## Your Options
1. Use suggestion 1
2. Use suggestion 2
3. Use suggestion 3
4. Refine with your own feedback
5. Approve and continue
6. Abort
"""


STAGE_02_UNTYPED = """\
# Stage 02: Hypothesis Generation

## Objective
Generate hypotheses.

## Previously Approved Stage Summaries
_None yet._

## What I Did
Brainstormed several ideas.

## Key Results
We think retrieval will help.

## Files Produced
- `workspace/notes/hypotheses.md` - notes

## Decision Ledger
- **Open Questions**: None
- **Locked Decisions**: None
- **Assumptions**: None
- **Rejected Alternatives**: None

## Suggestions for Refinement
1. Add stronger evidence.
2. Narrow the scope.
3. Compare with another baseline.

## Your Options
1. Use suggestion 1
2. Use suggestion 2
3. Use suggestion 3
4. Refine with your own feedback
5. Approve and continue
6. Abort
"""


class HypothesisManifestTests(unittest.TestCase):
    def _build_paths(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        run_root = Path(tmp_dir.name) / "run"
        paths = build_run_paths(run_root)
        ensure_run_layout(paths)
        write_text(paths.notes_dir / "hypotheses.md", "# Notes\n")
        write_text(paths.user_input, "test goal")
        initialize_memory(paths, "test goal")
        ensure_run_config(paths, model="sonnet", venue="neurips_2025")
        return paths

    def test_stage02_validation_requires_typed_sections(self) -> None:
        paths = self._build_paths()

        problems = validate_stage_markdown(STAGE_02_UNTYPED, stage=STAGES[1], paths=paths)

        self.assertTrue(any("typed subsections" in problem for problem in problems))

    def test_write_hypothesis_manifest_parses_typed_claims(self) -> None:
        paths = self._build_paths()

        manifest = write_hypothesis_manifest(paths, STAGE_02_TYPED)
        loaded = load_hypothesis_manifest(paths.hypothesis_manifest)

        self.assertIsNotNone(manifest)
        assert loaded is not None
        self.assertEqual(loaded.theoretical_propositions[0].identifier, "T1")
        self.assertEqual(loaded.empirical_hypotheses[0].identifier, "H1")
        self.assertEqual(loaded.paper_claims[0].identifier, "C1")
        self.assertIn("retrieval augmentation", loaded.empirical_hypotheses[0].statement.lower())

    def test_build_hypothesis_context_uses_manifest(self) -> None:
        paths = self._build_paths()
        write_hypothesis_manifest(paths, STAGE_02_TYPED)

        context = build_hypothesis_context(paths)

        self.assertIsNotNone(context)
        assert context is not None
        self.assertIn("### Empirical Hypotheses", context)
        self.assertIn("**H1**", context)
        self.assertIn("Verification", context)

    def test_stage03_prompt_injects_hypothesis_context(self) -> None:
        paths = self._build_paths()
        write_hypothesis_manifest(paths, STAGE_02_TYPED)
        write_stage_handoff(paths, STAGES[0], (
            "# Stage 01: Literature Survey\n\n"
            "## Objective\nSurvey the space.\n\n"
            "## Key Results\nLong-context degradation remains unresolved.\n\n"
            "## Files Produced\n- `workspace/notes/survey.md`\n"
        ))

        repo_root = Path(__file__).resolve().parent.parent
        ui = TerminalUI()
        operator = ClaudeOperator(model="sonnet", fake_mode=True, ui=ui)
        manager = ResearchManager(project_root=repo_root, runs_dir=paths.run_root.parent, operator=operator, ui=ui)

        prompt = manager._build_stage_prompt(paths, STAGES[2], None, False)

        self.assertIn("Hypothesis Context (from Stage 02)", prompt)
        self.assertIn("Theoretical Propositions", prompt)
        self.assertIn("Empirical Hypotheses", prompt)
        self.assertIn("Paper Claims (Provisional)", prompt)


if __name__ == "__main__":
    unittest.main()
