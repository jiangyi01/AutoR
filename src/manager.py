from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TextIO

from .operator import ClaudeOperator
from .utils import (
    STAGES,
    RunPaths,
    StageSpec,
    append_approved_stage_summary,
    append_log_entry,
    build_prompt,
    build_run_paths,
    canonicalize_stage_markdown,
    create_run_root,
    ensure_run_layout,
    format_stage_template,
    initialize_memory,
    load_prompt_template,
    parse_refinement_suggestions,
    read_text,
    truncate_text,
    validate_stage_markdown,
    write_text,
)


class ResearchManager:
    def __init__(
        self,
        project_root: Path,
        runs_dir: Path,
        operator: ClaudeOperator,
        output_stream: TextIO = sys.stdout,
    ) -> None:
        self.project_root = project_root
        self.runs_dir = runs_dir
        self.operator = operator
        self.prompt_dir = self.project_root / "src" / "prompts"
        self.output_stream = output_stream

    def run(self, user_goal: str) -> bool:
        paths = self._create_run(user_goal)
        self._print(f"Run created at: {paths.run_root}")

        for stage in STAGES:
            approved = self._run_stage(paths, stage)
            if not approved:
                append_log_entry(
                    paths.logs,
                    "run_aborted",
                    f"Run aborted during {stage.stage_title}.",
                )
                self._print("Run aborted.")
                return False

        append_log_entry(paths.logs, "run_complete", "All stages approved.")
        self._print("All stages approved. Run complete.")
        return True

    def _create_run(self, user_goal: str) -> RunPaths:
        run_root = create_run_root(self.runs_dir)
        paths = build_run_paths(run_root)
        ensure_run_layout(paths)
        write_text(paths.user_input, user_goal)
        initialize_memory(paths, user_goal)
        append_log_entry(paths.logs, "run_start", f"Run root: {paths.run_root}")
        return paths

    def _run_stage(self, paths: RunPaths, stage: StageSpec) -> bool:
        attempt_no = 1
        revision_feedback: str | None = None

        while True:
            self._print(f"\nRunning {stage.stage_title} (attempt {attempt_no})...")
            prompt = self._build_stage_prompt(paths, stage, revision_feedback)
            append_log_entry(
                paths.logs,
                f"{stage.slug} attempt {attempt_no} prompt",
                prompt,
            )

            result = self.operator.run_stage(stage, prompt, paths, attempt_no)
            append_log_entry(
                paths.logs,
                f"{stage.slug} attempt {attempt_no} result",
                (
                    f"success: {result.success}\n"
                    f"exit_code: {result.exit_code}\n"
                    f"stage_file_path: {result.stage_file_path}\n"
                    f"final_stage_file_path: {paths.stage_file(stage)}\n\n"
                    "stdout:\n"
                    f"{result.stdout or '(empty)'}\n\n"
                    "stderr:\n"
                    f"{result.stderr or '(empty)'}"
                ),
            )

            if not result.stage_file_path.exists():
                self._print(
                    f"Stage summary draft missing for {stage.stage_title}. Running repair attempt..."
                )
                append_log_entry(
                    paths.logs,
                    f"{stage.slug} attempt {attempt_no} repair_triggered",
                    "Primary attempt did not produce stage summary draft. Triggering repair pass.",
                )
                repair_result = self.operator.repair_stage_summary(
                    stage=stage,
                    original_prompt=prompt,
                    original_result=result,
                    paths=paths,
                    attempt_no=attempt_no,
                )
                append_log_entry(
                    paths.logs,
                    f"{stage.slug} attempt {attempt_no} repair_result",
                    (
                        f"success: {repair_result.success}\n"
                        f"exit_code: {repair_result.exit_code}\n"
                        f"stage_file_path: {repair_result.stage_file_path}\n\n"
                        "stdout:\n"
                        f"{repair_result.stdout or '(empty)'}\n\n"
                        "stderr:\n"
                        f"{repair_result.stderr or '(empty)'}"
                    ),
                )
                result = repair_result

            if not result.stage_file_path.exists():
                raise RuntimeError(
                    f"Stage summary draft was not generated for {stage.slug}: {result.stage_file_path}"
                )

            stage_markdown = read_text(result.stage_file_path)
            validation_errors = validate_stage_markdown(stage_markdown)
            if validation_errors:
                self._print(
                    f"Stage summary for {stage.stage_title} was incomplete. Running repair attempt..."
                )
                append_log_entry(
                    paths.logs,
                    f"{stage.slug} attempt {attempt_no} validation_failed",
                    "\n".join(validation_errors),
                )
                repair_result = self.operator.repair_stage_summary(
                    stage=stage,
                    original_prompt=prompt,
                    original_result=result,
                    paths=paths,
                    attempt_no=attempt_no,
                )
                append_log_entry(
                    paths.logs,
                    f"{stage.slug} attempt {attempt_no} repair_result",
                    (
                        f"success: {repair_result.success}\n"
                        f"exit_code: {repair_result.exit_code}\n"
                        f"stage_file_path: {repair_result.stage_file_path}\n\n"
                        "stdout:\n"
                        f"{repair_result.stdout or '(empty)'}\n\n"
                        "stderr:\n"
                        f"{repair_result.stderr or '(empty)'}"
                    ),
                )

                if not repair_result.stage_file_path.exists():
                    raise RuntimeError(
                        f"Stage summary repair failed for {stage.slug}: {repair_result.stage_file_path}"
                    )

                stage_markdown = read_text(repair_result.stage_file_path)
                validation_errors = validate_stage_markdown(stage_markdown)
                if validation_errors:
                    self._print(
                        f"Repair output for {stage.stage_title} is still incomplete. Normalizing locally..."
                    )
                    normalized_markdown = canonicalize_stage_markdown(
                        stage=stage,
                        memory_text=read_text(paths.memory),
                        markdown=stage_markdown,
                        fallback_text="\n\n".join(
                            part for part in [result.stdout, result.stderr, repair_result.stdout, repair_result.stderr] if part
                        ),
                    )
                    write_text(repair_result.stage_file_path, normalized_markdown)
                    append_log_entry(
                        paths.logs,
                        f"{stage.slug} attempt {attempt_no} local_normalization",
                        (
                            "Applied local stage markdown normalization after repair remained invalid.\n\n"
                            "Previous validation errors:\n"
                            + "\n".join(f"- {problem}" for problem in validation_errors)
                            + "\n\nNormalized markdown preview:\n"
                            + truncate_text(normalized_markdown, max_chars=6000)
                        ),
                    )

                    stage_markdown = read_text(repair_result.stage_file_path)
                    validation_errors = validate_stage_markdown(stage_markdown)
                    if validation_errors:
                        joined = "\n- ".join(validation_errors)
                        raise RuntimeError(
                            f"Invalid stage markdown for {stage.slug} after local normalization:\n- {joined}"
                        )

                result = repair_result

            final_stage_path = paths.stage_file(stage)
            shutil.copyfile(result.stage_file_path, final_stage_path)
            append_log_entry(
                paths.logs,
                f"{stage.slug} attempt {attempt_no} promoted",
                (
                    "Promoted validated stage summary draft to final stage file.\n"
                    f"draft: {result.stage_file_path}\n"
                    f"final: {final_stage_path}"
                ),
            )
            stage_markdown = read_text(final_stage_path)

            self._display_stage_output(stage, stage_markdown)
            choice = self._ask_choice()
            append_log_entry(
                paths.logs,
                f"{stage.slug} attempt {attempt_no} user_choice",
                f"choice: {choice}",
            )

            if choice in {"1", "2", "3"}:
                suggestions = parse_refinement_suggestions(stage_markdown)
                selected = suggestions[int(choice) - 1]
                revision_feedback = (
                    "Rerun the current stage from scratch and address this refinement request:\n"
                    f"{selected}"
                )
                attempt_no += 1
                continue

            if choice == "4":
                custom_feedback = self._read_multiline_feedback()
                revision_feedback = (
                    "Rerun the current stage from scratch and address this user feedback:\n"
                    f"{custom_feedback}"
                )
                append_log_entry(
                    paths.logs,
                    f"{stage.slug} attempt {attempt_no} custom_feedback",
                    custom_feedback,
                )
                attempt_no += 1
                continue

            if choice == "5":
                append_approved_stage_summary(paths.memory, stage, stage_markdown)
                append_log_entry(
                    paths.logs,
                    f"{stage.slug} approved",
                    "Stage approved and appended to memory.",
                )
                self._print(f"Approved {stage.stage_title}.")
                return True

            if choice == "6":
                return False

    def _build_stage_prompt(
        self,
        paths: RunPaths,
        stage: StageSpec,
        revision_feedback: str | None,
    ) -> str:
        template = load_prompt_template(self.prompt_dir, stage)
        stage_template = format_stage_template(template, stage, paths)
        user_request = read_text(paths.user_input)
        approved_memory = read_text(paths.memory)
        return build_prompt(stage, stage_template, user_request, approved_memory, revision_feedback)

    def _display_stage_output(self, stage: StageSpec, markdown: str) -> None:
        divider = "=" * 80
        self._print(f"\n{divider}")
        self._print(stage.stage_title)
        self._print(divider)
        self._print(markdown.rstrip())
        self._print(divider)

    def _ask_choice(self) -> str:
        valid = {"1", "2", "3", "4", "5", "6"}
        while True:
            choice = input("Enter your choice:\n> ").strip()
            if choice in valid:
                return choice
            self._print("Invalid choice. Enter one of: 1, 2, 3, 4, 5, 6.")

    def _read_multiline_feedback(self) -> str:
        self._print("Enter custom feedback. Finish with an empty line:")
        lines: list[str] = []

        while True:
            prompt = "> " if not lines else ""
            line = input(prompt)
            if not line.strip():
                if lines:
                    break
                self._print("Feedback cannot be empty.")
                continue
            lines.append(line.rstrip())

        return "\n".join(lines).strip()

    def _print(self, text: str) -> None:
        print(text, file=self.output_stream)
