from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.manager import ResearchManager
from src.manifest import load_run_manifest
from src.project_bootstrap import StageAssessment
from src.utils import (
    DEFAULT_REFINEMENT_SUGGESTIONS,
    INTAKE_STAGE,
    STAGES,
    OperatorResult,
    approved_stage_summaries,
    build_run_paths,
    read_text,
    relative_to_run,
    write_text,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
STAGE_01 = next(stage for stage in STAGES if stage.slug == "01_literature_survey")
STAGE_05 = next(stage for stage in STAGES if stage.slug == "05_experimentation")
STAGE_06 = next(stage for stage in STAGES if stage.slug == "06_analysis")


class ScriptedSmokeOperator:
    def __init__(self) -> None:
        self.model = "smoke-test-model"
        self.invocations: dict[str, int] = {}
        self.continue_modes: dict[str, list[bool]] = {}
        self.prompts: dict[str, list[str]] = {}

    def run_stage(
        self,
        stage,
        prompt: str,
        paths,
        attempt_no: int,
        continue_session: bool = False,
    ) -> OperatorResult:
        invocation = self.invocations.get(stage.slug, 0) + 1
        self.invocations[stage.slug] = invocation
        self.continue_modes.setdefault(stage.slug, []).append(continue_session)
        self.prompts.setdefault(stage.slug, []).append(prompt)
        produced = self._materialize_artifacts(stage, paths, invocation)
        stage_file = paths.stage_tmp_file(stage)
        write_text(
            stage_file,
            self._build_stage_markdown(
                stage,
                paths,
                invocation,
                produced,
                continue_session,
                len(prompt.split()),
            ),
        )
        return OperatorResult(
            success=True,
            exit_code=0,
            stdout=f"scripted invocation {invocation}",
            stderr="",
            stage_file_path=stage_file,
            session_id=f"{stage.slug}-session-{invocation}",
        )

    def repair_stage_summary(
        self,
        stage,
        original_prompt: str,
        original_result: OperatorResult,
        paths,
        attempt_no: int,
    ) -> OperatorResult:
        return self.run_stage(stage, original_prompt, paths, attempt_no, continue_session=False)

    def _materialize_artifacts(self, stage, paths, invocation: int) -> list[str]:
        produced: list[str] = []

        if stage.slug == "bootstrap":
            profile_files = {
                paths.profile_dir / "research_profile.json": json.dumps(
                    {
                        "themes": ["reasoning"],
                        "terminology": ["chain-of-thought"],
                        "methods": ["prompting"],
                        "venues": ["NeurIPS"],
                        "confidence": "medium",
                        "summary": "Researcher focused on reasoning workflows.",
                    }
                ),
                paths.profile_dir / "citation_neighborhood.json": json.dumps(
                    {
                        "frequently_cited": [
                            {"title": "Chain-of-Thought Prompting", "authors": "Wei et al.", "year": "2022"},
                        ],
                        "related_authors": ["Wei et al."],
                        "key_venues": ["NeurIPS"],
                        "seed_papers": [
                            {
                                "title": "Chain-of-Thought Prompting",
                                "authors": "Wei et al.",
                                "year": "2022",
                                "why": "Foundational reasoning prior.",
                            }
                        ],
                    }
                ),
                paths.profile_dir / "style_profile.json": json.dumps(
                    {
                        "voice": "mixed",
                        "person": "first_plural",
                        "formality": "formal",
                        "avg_section_count": 6,
                        "section_ordering": ["Introduction", "Method", "Experiments", "Conclusion"],
                        "abstract_pattern": "problem-method-result",
                        "notation_conventions": ["boldface for vectors"],
                        "paragraph_style": "topic-sentence-first",
                        "notes": "Prefers concise academic prose.",
                    }
                ),
                paths.profile_dir / "style_notes.md": "# Writing Style Profile\n\n- Formal and concise.\n",
                paths.profile_dir / "bootstrap_summary.md": "This corpus suggests a reasoning-focused researcher profile.\n",
                paths.profile_dir / "corpus_manifest.json": json.dumps(
                    {
                        "corpus_path": str(paths.run_root / "paper_corpus"),
                        "scanned_at": "2026-04-08T00:00:00",
                        "total_files_found": 2,
                        "files_processed": 2,
                        "files_skipped": 0,
                        "skipped_reasons": [],
                        "papers": [],
                    }
                ),
            }
            for path, content in profile_files.items():
                write_text(path, content)
                produced.append(relative_to_run(path, paths.run_root))

        note_path = paths.notes_dir / f"{stage.slug}_smoke_note.md"
        write_text(note_path, f"# Smoke Note\n\nStage: {stage.slug}\nInvocation: {invocation}\n")
        produced.append(relative_to_run(note_path, paths.run_root))

        if stage.number >= 3:
            data_path = paths.data_dir / "study_design.json"
            write_text(
                data_path,
                json.dumps({"stage": stage.slug, "invocation": invocation, "dataset": "smoke"}),
            )
            produced.append(relative_to_run(data_path, paths.run_root))

        if stage.number >= 4:
            code_path = paths.code_dir / "train.py"
            write_text(code_path, "print('smoke experiment entrypoint')\n")
            produced.append(relative_to_run(code_path, paths.run_root))

        if stage.number >= 5:
            result_path = paths.results_dir / "metrics.json"
            write_text(
                result_path,
                json.dumps({"stage": stage.slug, "invocation": invocation, "accuracy": 0.9}),
            )
            produced.append(relative_to_run(result_path, paths.run_root))

        if stage.number >= 6:
            figure_path = paths.figures_dir / "accuracy.png"
            figure_path.write_bytes(b"\x89PNG smoke image data")
            produced.append(relative_to_run(figure_path, paths.run_root))

        if stage.number >= 7:
            sections_dir = paths.writing_dir / "sections"
            sections_dir.mkdir(parents=True, exist_ok=True)
            write_text(
                paths.writing_dir / "main.tex",
                (
                    "% AutoR venue: neurips_2025\n"
                    "\\documentclass{article}\n"
                    "\\usepackage{neurips_2023}\n"
                    "\\begin{document}\n"
                    "\\input{sections/introduction}\n"
                    "\\end{document}\n"
                ),
            )
            write_text(paths.writing_dir / "references.bib", "@article{smoke2026, title={Smoke}, year={2026}}\n")
            write_text(sections_dir / "introduction.tex", "\\section{Introduction}\nSmoke content.\n")
            write_text(sections_dir / "method.tex", "\\section{Method}\nSmoke content.\n")
            (paths.artifacts_dir / "paper.pdf").write_bytes(b"%PDF-1.4 smoke paper")
            write_text(paths.artifacts_dir / "build_log.txt", "Final status: SUCCESS\n")
            write_text(
                paths.artifacts_dir / "citation_verification.json",
                json.dumps({"overall_status": "pass", "total_citations": 1}),
            )
            write_text(
                paths.artifacts_dir / "self_review.json",
                json.dumps({"overall_score": 8.5, "final_verdict": "ready", "rounds": 1}),
            )
            produced.extend(
                [
                    relative_to_run(paths.writing_dir / "main.tex", paths.run_root),
                    relative_to_run(paths.artifacts_dir / "paper.pdf", paths.run_root),
                ]
            )

        if stage.number >= 8:
            review_path = paths.reviews_dir / "readiness.md"
            write_text(review_path, "# Readiness\n\n- Ready for smoke release.\n")
            produced.append(relative_to_run(review_path, paths.run_root))

        return produced

    def _build_stage_markdown(
        self,
        stage,
        paths,
        invocation: int,
        produced: list[str],
        continue_session: bool,
        prompt_word_count: int,
    ) -> str:
        prior = approved_stage_summaries(read_text(paths.memory))
        mode = "continuation" if continue_session else "fresh"
        files = "\n".join(f"- `{path}`" for path in produced)
        suggestions = "\n".join(
            f"{index}. {text}"
            for index, text in enumerate(DEFAULT_REFINEMENT_SUGGESTIONS, start=1)
        )

        return (
            f"# Stage {stage.number:02d}: {stage.display_name}\n\n"
            "## Objective\n"
            f"Produce a valid smoke-test stage summary for {stage.display_name}.\n\n"
            "## Previously Approved Stage Summaries\n"
            f"{prior}\n\n"
            "## What I Did\n"
            f"- Executed the scripted smoke operator in {mode} mode.\n"
            f"- Materialized the required artifacts for {stage.slug}.\n\n"
            "## Key Results\n"
            f"- Invocation marker: {invocation}\n"
            f"- Prompt words observed: {prompt_word_count}\n"
            "- The CLI workflow, validation, and approval loop all executed.\n\n"
            "## Files Produced\n"
            f"{files}\n\n"
            "## Suggestions for Refinement\n"
            f"{suggestions}\n\n"
            "## Your Options\n"
            "1. Use suggestion 1\n"
            "2. Use suggestion 2\n"
            "3. Use suggestion 3\n"
            "4. Refine with your own feedback\n"
            "5. Approve and continue\n"
            "6. Abort\n"
        )


class BootstrapAdjustingSmokeOperator(ScriptedSmokeOperator):
    def __init__(self, corrected_assessments: list[StageAssessment]) -> None:
        super().__init__()
        self.corrected_assessments = corrected_assessments

    def run_stage(
        self,
        stage,
        prompt: str,
        paths,
        attempt_no: int,
        continue_session: bool = False,
    ) -> OperatorResult:
        if stage.slug == "project_bootstrap":
            write_text(
                paths.bootstrap_dir / "stage_assessments.json",
                json.dumps([assessment.__dict__ for assessment in self.corrected_assessments], indent=2),
            )
        return super().run_stage(stage, prompt, paths, attempt_no, continue_session=continue_session)


class ManagerSmokeTests(unittest.TestCase):
    def _run_roots(self, runs_dir: Path) -> list[Path]:
        return sorted(path for path in runs_dir.iterdir() if path.is_dir())

    def _build_manager(self, tmp_dir: str) -> tuple[Path, ScriptedSmokeOperator, ResearchManager]:
        runs_dir = Path(tmp_dir) / "runs"
        operator = ScriptedSmokeOperator()
        manager = ResearchManager(
            project_root=REPO_ROOT,
            runs_dir=runs_dir,
            operator=operator,
            output_stream=io.StringIO(),
        )
        return runs_dir, operator, manager

    def test_manager_run_completes_full_eight_stage_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runs_dir, operator, manager = self._build_manager(tmp_dir)

            with patch.object(manager, "_ask_choice", return_value="5"):
                success = manager.run("Smoke-test the end-to-end AutoR flow.", venue="neurips_2025")

            self.assertTrue(success)
            run_root = self._run_roots(runs_dir)[0]
            paths = build_run_paths(run_root)
            self.assertTrue(paths.run_manifest.exists())
            self.assertTrue((paths.artifacts_dir / "paper_package" / "paper.pdf").exists())
            self.assertTrue((paths.artifacts_dir / "release_package" / "artifact_bundle_manifest.json").exists())
            self.assertTrue(paths.stage_file(STAGE_06).exists())

    def test_resume_run_from_redo_stage_reruns_downstream_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runs_dir, operator, manager = self._build_manager(tmp_dir)

            with patch.object(manager, "_ask_choice", return_value="5"):
                self.assertTrue(manager.run("Smoke-test redo-stage handling.", venue="neurips_2025"))

            run_root = self._run_roots(runs_dir)[0]
            paths = build_run_paths(run_root)
            initial_stage06 = read_text(paths.stage_file(STAGE_06))
            self.assertIn("Invocation marker: 1", initial_stage06)

            with patch.object(manager, "_ask_choice", return_value="5"):
                resumed = manager.resume_run(run_root, start_stage=STAGE_06, venue="neurips_2025")

            self.assertTrue(resumed)
            rerun_stage06 = read_text(paths.stage_file(STAGE_06))
            self.assertIn("Invocation marker: 2", rerun_stage06)
            self.assertIn("Invocation marker: 1", read_text(paths.stage_file(STAGES[4])))

    def test_stage_refinement_reuses_same_stage_before_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            _, operator, manager = self._build_manager(tmp_dir)
            paths = manager._create_run("Smoke-test stage refinement handling.", venue="neurips_2025")

            with patch.object(manager, "_ask_choice", side_effect=["1", "5"]):
                approved = manager._run_stage(paths, STAGE_01)

            self.assertTrue(approved)
            self.assertEqual(operator.continue_modes[STAGE_01.slug], [False, True])
            self.assertIn("Invocation marker: 2", read_text(paths.stage_file(STAGE_01)))

            manifest = load_run_manifest(paths.run_manifest)
            self.assertIsNotNone(manifest)
            assert manifest is not None
            entry = next(item for item in manifest.stages if item.slug == STAGE_01.slug)
            self.assertTrue(entry.approved)
            self.assertEqual(entry.attempt_count, 2)

    def test_resume_run_with_rollback_reruns_invalidated_downstream_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runs_dir, operator, manager = self._build_manager(tmp_dir)

            with patch.object(manager, "_ask_choice", return_value="5"):
                self.assertTrue(manager.run("Smoke-test rollback resume handling.", venue="neurips_2025"))

            run_root = self._run_roots(runs_dir)[0]
            paths = build_run_paths(run_root)
            self.assertIn("Invocation marker: 1", read_text(paths.stage_file(STAGE_05)))
            self.assertIn("Invocation marker: 1", read_text(paths.stage_file(STAGE_06)))

            with patch.object(manager, "_ask_choice", return_value="5"):
                resumed = manager.resume_run(run_root, rollback_stage=STAGE_05, venue="neurips_2025")

            self.assertTrue(resumed)
            self.assertIn("Invocation marker: 2", read_text(paths.stage_file(STAGE_05)))
            self.assertIn("Invocation marker: 2", read_text(paths.stage_file(STAGE_06)))
            self.assertEqual(operator.invocations[STAGE_05.slug], 2)
            self.assertEqual(operator.invocations[STAGE_06.slug], 2)
            self.assertIn("Invocation marker: 1", read_text(paths.stage_file(STAGES[3])))

    def test_manager_abort_marks_run_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runs_dir, _, manager = self._build_manager(tmp_dir)

            with patch.object(manager, "_ask_choice", return_value="6"):
                success = manager.run("Smoke-test abort handling.", venue="neurips_2025")

            self.assertFalse(success)
            run_root = self._run_roots(runs_dir)[0]
            paths = build_run_paths(run_root)
            manifest = load_run_manifest(paths.run_manifest)
            self.assertIsNotNone(manifest)
            assert manifest is not None
            self.assertEqual(manifest.run_status, "cancelled")
            self.assertEqual(manifest.current_stage_slug, INTAKE_STAGE.slug)
            self.assertIsNone(manifest.completed_at)

    def test_project_bootstrap_carries_forward_prior_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runs_dir, operator, manager = self._build_manager(tmp_dir)
            project_root = Path(tmp_dir) / "existing_project"
            project_root.mkdir()
            for name in ["main.py", "model.py", "train.py", "data.py", "utils.py", "eval.py"]:
                (project_root / name).write_text("# existing project code\n", encoding="utf-8")
            (project_root / "requirements.txt").write_text("torch\n", encoding="utf-8")

            with patch.object(manager, "_ask_choice", return_value="5"):
                success = manager.run(
                    "Adopt an existing project into AutoR.",
                    venue="neurips_2025",
                    project_root=project_root,
                )

            self.assertTrue(success)
            run_root = self._run_roots(runs_dir)[0]
            paths = build_run_paths(run_root)
            manifest = load_run_manifest(paths.run_manifest)
            self.assertIsNotNone(manifest)
            assert manifest is not None
            for stage in STAGES[:4]:
                entry = next(item for item in manifest.stages if item.slug == stage.slug)
                self.assertTrue(entry.approved)
                self.assertTrue(paths.stage_file(stage).exists())
            self.assertNotIn(STAGE_01.slug, operator.invocations)
            self.assertIn(STAGE_05.slug, operator.invocations)
            memory_text = read_text(paths.memory)
            self.assertIn("Stage 00: Research Intake", memory_text)
            self.assertIn("Stage 01: Literature Survey", memory_text)
            self.assertIn("Stage 04: Implementation", memory_text)
            self.assertNotIn("Stage -1: Project Repo Bootstrap", memory_text)

    def test_project_bootstrap_uses_corrected_stage_assessments_for_entry_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runs_dir = Path(tmp_dir) / "runs"
            corrected = [
                StageAssessment(1, "Literature Survey", "complete", "medium", ["bootstrap-approved"]),
                StageAssessment(2, "Hypothesis Generation", "complete", "medium", ["bootstrap-approved"]),
                StageAssessment(3, "Study Design", "not_started", "high", ["design gap remains"]),
                StageAssessment(4, "Implementation", "complete", "high", ["implementation exists"]),
                StageAssessment(5, "Experimentation", "not_started", "medium", ["no reliable experiment results"]),
                StageAssessment(6, "Analysis", "not_started", "medium", ["no reliable analysis"]),
                StageAssessment(7, "Writing", "not_started", "medium", ["no usable manuscript"]),
                StageAssessment(8, "Dissemination", "not_started", "medium", ["no dissemination artifacts"]),
            ]
            operator = BootstrapAdjustingSmokeOperator(corrected)
            manager = ResearchManager(
                project_root=REPO_ROOT,
                runs_dir=runs_dir,
                operator=operator,
                output_stream=io.StringIO(),
            )
            project_root = Path(tmp_dir) / "existing_project"
            project_root.mkdir()
            for name in ["main.py", "model.py", "train.py", "eval.py"]:
                (project_root / name).write_text("# existing project code\n", encoding="utf-8")
            (project_root / "requirements.txt").write_text("torch\n", encoding="utf-8")

            with patch.object(manager, "_ask_choice", return_value="5"):
                success = manager.run(
                    "Adopt an existing project with a bootstrap correction.",
                    venue="neurips_2025",
                    project_root=project_root,
                )

            self.assertTrue(success)
            self.assertIn(STAGES[2].slug, operator.invocations)
            self.assertNotIn(STAGE_01.slug, operator.invocations)
            self.assertNotIn(STAGES[1].slug, operator.invocations)

    def test_paper_corpus_bootstrap_injects_profile_into_downstream_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runs_dir, operator, manager = self._build_manager(tmp_dir)
            corpus_root = Path(tmp_dir) / "paper_corpus"
            corpus_root.mkdir()
            (corpus_root / "paper.tex").write_text(
                (
                    "\\title{Prior Work}\n"
                    "\\begin{document}\n"
                    "\\begin{abstract}We study reasoning workflows.\\end{abstract}\n"
                    "\\section{Introduction}Prior text.\n"
                    "\\end{document}\n"
                ),
                encoding="utf-8",
            )
            (corpus_root / "refs.bib").write_text(
                (
                    "@article{cot2022,\n"
                    "  title={Chain-of-Thought Prompting},\n"
                    "  author={Wei et al.},\n"
                    "  year={2022},\n"
                    "  journal={NeurIPS}\n"
                    "}\n"
                ),
                encoding="utf-8",
            )

            with patch.object(manager, "_ask_choice", return_value="5"):
                success = manager.run(
                    "Use my prior papers to align the new project.",
                    venue="neurips_2025",
                    paper_corpus=corpus_root,
                )

            self.assertTrue(success)
            run_root = self._run_roots(runs_dir)[0]
            paths = build_run_paths(run_root)
            self.assertIn("bootstrap", operator.invocations)
            self.assertTrue((paths.profile_dir / "research_profile.json").exists())
            self.assertTrue((paths.profile_dir / "style_profile.json").exists())
            stage01_prompt = operator.prompts[STAGE_01.slug][0]
            self.assertIn("Researcher Profile (from paper corpus bootstrap)", stage01_prompt)
            self.assertIn("Seed papers for literature search", stage01_prompt)
            memory_text = read_text(paths.memory)
            self.assertNotIn("Stage -1", memory_text)


if __name__ == "__main__":
    unittest.main()
