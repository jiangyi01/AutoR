"""Tests for structured cross-stage Decision Ledger (Issue #34).

Validates that:
- Decision Ledger appears in the required stage output template.
- render_approved_stage_entry includes Decision Ledger when present.
- write_stage_handoff includes Decision Ledger when present.
- build_decision_ledger_context aggregates ledgers from prior stages.
- Stage prompts inject accumulated ledger context for stage 2+.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from src.utils import (
    STAGES,
    build_decision_ledger_context,
    build_handoff_context,
    build_run_paths,
    create_run_root,
    ensure_run_layout,
    initialize_memory,
    initialize_run_config,
    read_text,
    render_approved_stage_entry,
    required_stage_output_template,
    validate_stage_markdown,
    write_stage_handoff,
    write_text,
)


SAMPLE_STAGE_MARKDOWN = """\
# Stage 01: Literature Survey

## Objective
Survey the field.

## Previously Approved Stage Summaries
_None yet._

## What I Did
Read 20 papers.

## Key Results
Found 3 key gaps.

## Files Produced
- `workspace/notes/survey.md` - literature notes

## Decision Ledger
- **Open Questions**: Can method X scale to large datasets?
- **Locked Decisions**: Focus on transformer-based approaches (rationale: best performance on benchmarks)
- **Assumptions**: Training data is i.i.d.
- **Rejected Alternatives**: RNN-based methods (too slow for target scale)

## Suggestions for Refinement
1. Expand survey to include 2024 papers.
2. Add quantitative comparison table.
3. Include industrial applications.

## Your Options
1. Use suggestion 1
2. Use suggestion 2
3. Use suggestion 3
4. Refine with your own feedback
5. Approve and continue
6. Abort
"""

SAMPLE_STAGE_MARKDOWN_NO_LEDGER = """\
# Stage 02: Hypothesis Generation

## Objective
Generate hypotheses.

## Previously Approved Stage Summaries
_None yet._

## What I Did
Brainstormed ideas.

## Key Results
3 hypotheses proposed.

## Files Produced
- `workspace/notes/hypotheses.md` - hypothesis list

## Suggestions for Refinement
1. Refine hypothesis 1.
2. Add baseline comparison.
3. Strengthen theoretical motivation.

## Your Options
1. Use suggestion 1
2. Use suggestion 2
3. Use suggestion 3
4. Refine with your own feedback
5. Approve and continue
6. Abort
"""


class TestOutputTemplateIncludesLedger(unittest.TestCase):
    def test_template_contains_decision_ledger_section(self):
        template = required_stage_output_template(STAGES[0])
        self.assertIn("## Decision Ledger", template)
        self.assertIn("Open Questions", template)
        self.assertIn("Locked Decisions", template)
        self.assertIn("Assumptions", template)
        self.assertIn("Rejected Alternatives", template)

    def test_ledger_appears_before_suggestions(self):
        template = required_stage_output_template(STAGES[0])
        ledger_pos = template.index("## Decision Ledger")
        suggestions_pos = template.index("## Suggestions for Refinement")
        self.assertLess(ledger_pos, suggestions_pos)


class TestRenderApprovedStageEntry(unittest.TestCase):
    def test_keeps_approved_memory_compact_when_ledger_present(self):
        entry = render_approved_stage_entry(STAGES[0], SAMPLE_STAGE_MARKDOWN)
        self.assertNotIn("Decision Ledger", entry)
        self.assertIn("Read 20 papers", entry)
        self.assertIn("Found 3 key gaps", entry)

    def test_omits_decision_ledger_when_absent(self):
        entry = render_approved_stage_entry(STAGES[1], SAMPLE_STAGE_MARKDOWN_NO_LEDGER)
        self.assertNotIn("Decision Ledger", entry)
        # Should still have the other sections
        self.assertIn("Brainstormed ideas", entry)


class TestWriteStageHandoff(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.runs_dir = Path(self.tmp) / "runs"
        self.runs_dir.mkdir()
        self.run_root = create_run_root(self.runs_dir)
        self.paths = build_run_paths(self.run_root)
        ensure_run_layout(self.paths)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_handoff_includes_decision_ledger(self):
        handoff_path = write_stage_handoff(self.paths, STAGES[0], SAMPLE_STAGE_MARKDOWN)
        content = read_text(handoff_path)
        self.assertIn("## Decision Ledger", content)
        self.assertIn("Training data is i.i.d.", content)

    def test_handoff_omits_ledger_when_absent(self):
        handoff_path = write_stage_handoff(self.paths, STAGES[1], SAMPLE_STAGE_MARKDOWN_NO_LEDGER)
        content = read_text(handoff_path)
        self.assertNotIn("Decision Ledger", content)

    def test_handoff_context_strips_ledger_to_avoid_prompt_duplication(self):
        write_stage_handoff(self.paths, STAGES[0], SAMPLE_STAGE_MARKDOWN)
        handoff_context = build_handoff_context(self.paths, upto_stage=STAGES[1])
        self.assertIn("Handoff: Stage 01: Literature Survey", handoff_context)
        self.assertNotIn("Decision Ledger", handoff_context)


class TestBuildDecisionLedgerContext(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.runs_dir = Path(self.tmp) / "runs"
        self.runs_dir.mkdir()
        self.run_root = create_run_root(self.runs_dir)
        self.paths = build_run_paths(self.run_root)
        ensure_run_layout(self.paths)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_none_when_no_handoffs(self):
        result = build_decision_ledger_context(self.paths)
        self.assertIsNone(result)

    def test_returns_none_when_no_ledger_in_handoffs(self):
        write_stage_handoff(self.paths, STAGES[1], SAMPLE_STAGE_MARKDOWN_NO_LEDGER)
        result = build_decision_ledger_context(self.paths)
        self.assertIsNone(result)

    def test_collects_ledger_from_single_stage(self):
        write_stage_handoff(self.paths, STAGES[0], SAMPLE_STAGE_MARKDOWN)
        result = build_decision_ledger_context(self.paths)
        self.assertIsNotNone(result)
        self.assertIn("transformer-based approaches", result)
        self.assertIn("Training data is i.i.d.", result)
        self.assertIn("Literature Survey", result)

    def test_collects_ledger_from_multiple_stages(self):
        write_stage_handoff(self.paths, STAGES[0], SAMPLE_STAGE_MARKDOWN)
        # Create a second stage with ledger
        stage2_md = SAMPLE_STAGE_MARKDOWN_NO_LEDGER.replace(
            "## Suggestions for Refinement",
            "## Decision Ledger\n"
            "- **Open Questions**: How to handle class imbalance?\n"
            "- **Locked Decisions**: Use cross-entropy loss\n"
            "- **Assumptions**: None additional\n"
            "- **Rejected Alternatives**: Focal loss (marginal improvement)\n\n"
            "## Suggestions for Refinement",
        )
        write_stage_handoff(self.paths, STAGES[1], stage2_md)
        result = build_decision_ledger_context(self.paths)
        self.assertIsNotNone(result)
        self.assertIn("transformer-based approaches", result)
        self.assertIn("class imbalance", result)

    def test_upto_stage_filters_correctly(self):
        write_stage_handoff(self.paths, STAGES[0], SAMPLE_STAGE_MARKDOWN)
        stage2_md = SAMPLE_STAGE_MARKDOWN_NO_LEDGER.replace(
            "## Suggestions for Refinement",
            "## Decision Ledger\n"
            "- **Open Questions**: How to handle class imbalance?\n\n"
            "## Suggestions for Refinement",
        )
        write_stage_handoff(self.paths, STAGES[1], stage2_md)
        # Only get stage 01's ledger (upto stage 02 excludes stage 02)
        result = build_decision_ledger_context(self.paths, upto_stage=STAGES[1])
        self.assertIsNotNone(result)
        self.assertIn("transformer-based approaches", result)
        self.assertNotIn("class imbalance", result)


class TestStagePromptIncludesLedger(unittest.TestCase):
    """Test that _build_stage_prompt injects ledger context for stage 2+."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.runs_dir = Path(self.tmp) / "runs"
        self.runs_dir.mkdir()
        self.run_root = create_run_root(self.runs_dir)
        self.paths = build_run_paths(self.run_root)
        ensure_run_layout(self.paths)
        initialize_run_config(self.paths, model="sonnet", venue="neurips_2025")
        initialize_memory(self.paths, "Test goal")
        write_text(self.paths.user_input, "Test goal")
        # Write a handoff with ledger for stage 01
        write_stage_handoff(self.paths, STAGES[0], SAMPLE_STAGE_MARKDOWN)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ledger_injected_for_stage_02(self):
        from src.manager import ResearchManager
        from src.operator import ClaudeOperator
        from src.terminal_ui import TerminalUI

        repo_root = Path(__file__).resolve().parent.parent
        ui = TerminalUI()
        operator = ClaudeOperator(model="sonnet", fake_mode=True, ui=ui)
        manager = ResearchManager(
            project_root=repo_root, runs_dir=self.runs_dir,
            operator=operator, ui=ui,
        )
        prompt = manager._build_stage_prompt(self.paths, STAGES[1], None, False)
        self.assertIn("Decision Ledger (from prior stages)", prompt)
        self.assertIn("transformer-based approaches", prompt)
        self.assertIn("Respect locked decisions", prompt)


class TestDecisionLedgerValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.runs_dir = Path(self.tmp) / "runs"
        self.runs_dir.mkdir()
        self.run_root = create_run_root(self.runs_dir)
        self.paths = build_run_paths(self.run_root)
        ensure_run_layout(self.paths)
        note_path = self.paths.notes_dir / "survey.md"
        write_text(note_path, "survey note")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_validation_requires_decision_ledger_section(self):
        problems = validate_stage_markdown(
            SAMPLE_STAGE_MARKDOWN_NO_LEDGER.replace(
                "# Stage 02: Hypothesis Generation",
                "# Stage 01: Literature Survey",
            ),
            stage=STAGES[0],
            paths=self.paths,
        )
        self.assertTrue(any("Missing required section: Decision Ledger" in problem for problem in problems))

    def test_validation_requires_structured_decision_ledger_markers(self):
        malformed = SAMPLE_STAGE_MARKDOWN.replace(
            "## Decision Ledger\n"
            "- **Open Questions**: Can method X scale to large datasets?\n"
            "- **Locked Decisions**: Focus on transformer-based approaches (rationale: best performance on benchmarks)\n"
            "- **Assumptions**: Training data is i.i.d.\n"
            "- **Rejected Alternatives**: RNN-based methods (too slow for target scale)\n\n",
            "## Decision Ledger\nFree-form notes only.\n\n",
        )
        problems = validate_stage_markdown(malformed, stage=STAGES[0], paths=self.paths)
        self.assertTrue(any("Decision Ledger" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()
