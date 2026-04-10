from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

from src.artifact_index import write_artifact_index
from src.manifest import initialize_run_manifest, mark_stage_approved_manifest, mark_stage_human_review_manifest
from src.studio_http import create_server
from src.utils import STAGES, build_run_paths, ensure_run_layout, initialize_run_config, write_text


STAGE_01 = next(stage for stage in STAGES if stage.slug == "01_literature_survey")
STAGE_02 = next(stage for stage in STAGES if stage.slug == "02_hypothesis_generation")
STAGE_03 = next(stage for stage in STAGES if stage.slug == "03_study_design")
STAGE_04 = next(stage for stage in STAGES if stage.slug == "04_implementation")
STAGE_05 = next(stage for stage in STAGES if stage.slug == "05_experimentation")


class StudioHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tempdir.name)
        self.runs_dir = self.repo_root / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_root = self.repo_root / ".autor-test"
        self.run_id = self._create_run("20260409_303030")
        self.server = create_server(
            repo_root=self.repo_root,
            host="127.0.0.1",
            port=0,
            runs_dir=self.runs_dir,
            metadata_root=self.metadata_root,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"
        self._opener = build_opener(ProxyHandler({}))

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def test_healthz(self) -> None:
        payload = self._request_json("GET", "/healthz")
        self.assertEqual(payload["status"], "ok")

    def test_studio_shell_serves_index_html(self) -> None:
        request = Request(self.base_url + "/studio/", method="GET")
        with self._opener.open(request) as response:
            body = response.read().decode("utf-8")
        self.assertIn("AutoR Studio", body)
        self.assertIn("Research Control Workspace", body)
        self.assertIn("Human Review", body)
        self.assertIn("Paper Preview", body)

    def test_project_endpoints(self) -> None:
        created = self._request_json(
            "POST",
            "/api/projects",
            {
                "title": "Reasoning Bench",
                "thesis": "Track benchmark experiments.",
                "tags": ["bench", "reasoning"],
            },
        )
        self.assertEqual(created["project_id"], "reasoning-bench")
        self.assertEqual(created["participation_model"], "human_in_loop")

        attached = self._request_json(
            "POST",
            f"/api/projects/{created['project_id']}/runs",
            {"run_id": self.run_id, "make_active": True},
        )
        self.assertEqual(attached["active_run_id"], self.run_id)

        listed = self._request_json("GET", "/api/projects")
        self.assertEqual(len(listed["projects"]), 1)
        self.assertEqual(listed["projects"][0]["run_ids"], [self.run_id])

        overview = self._request_json("GET", "/api/projects/overview")
        self.assertEqual(overview["projects"][0]["active_run_id"], self.run_id)
        self.assertEqual(overview["projects"][0]["latest_run_status"], "human_review")

        detail = self._request_json("GET", f"/api/projects/{created['project_id']}")
        self.assertEqual(detail["project_id"], created["project_id"])
        self.assertEqual(detail["latest_completed_stage_slug"], STAGE_04.slug)

    def test_history_endpoint(self) -> None:
        history = self._request_json("GET", f"/api/runs/{self.run_id}/history")
        self.assertEqual(history["run_id"], self.run_id)
        self.assertTrue(any(version["kind"] == "auto_checkpoint" for version in history["versions"]))
        self.assertTrue(any(version["kind"] == "awaiting_review" for version in history["versions"]))
        self.assertTrue(any(event["title"] == "Run Started" for event in history["trace_events"]))
        self.assertTrue(any(event["actor"] == "human" for event in history["trace_events"]))

    def test_run_and_stage_endpoints(self) -> None:
        summary = self._request_json("GET", f"/api/runs/{self.run_id}")
        self.assertEqual(summary["run_status"], "human_review")
        self.assertEqual(summary["current_stage_slug"], STAGE_05.slug)

        stage = self._request_json("GET", f"/api/runs/{self.run_id}/stages/{STAGE_01.slug}")
        self.assertIn("# Stage 01: Literature Survey", stage["markdown"])

        artifacts = self._request_json("GET", f"/api/runs/{self.run_id}/artifacts")
        self.assertEqual(artifacts["artifact_count"], 3)

    def test_paper_endpoints(self) -> None:
        preview = self._request_json("GET", f"/api/runs/{self.run_id}/paper")
        self.assertTrue(preview["pdf_available"])
        self.assertEqual(preview["pdf_relative_path"], "workspace/artifacts/paper.pdf")
        self.assertEqual(preview["tex_relative_path"], "workspace/writing/main.tex")
        self.assertIn("workspace/writing/sections/intro.tex", preview["section_paths"])
        self.assertIn("latexmk -pdf main.tex", preview["build_log_content"])

        request = Request(self.base_url + f"/api/runs/{self.run_id}/paper/pdf", method="GET")
        with self._opener.open(request) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type")
        self.assertEqual(content_type, "application/pdf")
        self.assertTrue(body.startswith(b"%PDF-1.4"))

    def test_file_tree_and_content_endpoints(self) -> None:
        tree = self._request_json("GET", f"/api/runs/{self.run_id}/files/tree?root=workspace&depth=2")
        self.assertEqual(tree["rel_path"], "workspace")

        content = self._request_json(
            "GET",
            f"/api/runs/{self.run_id}/files/content?path=workspace/literature/survey_notes.md",
        )
        self.assertEqual(content["encoding"], "utf-8")
        self.assertIn("Core evidence", content["content"])

    def test_iteration_plan_endpoint(self) -> None:
        plan = self._request_json(
            "POST",
            f"/api/runs/{self.run_id}/iterations/plan",
            {
                "base_stage_slug": STAGE_03.slug,
                "scope_type": "stage",
                "scope_value": STAGE_03.slug,
                "mode": "redo",
            },
        )
        self.assertEqual(plan["base_stage_slug"], STAGE_03.slug)
        self.assertEqual(plan["stale_stages"], [STAGE_04.slug, STAGE_05.slug])
        self.assertTrue(plan["reuses_current_run"])

    def _request_json(self, method: str, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        with self._opener.open(request) as response:
            return json.loads(response.read().decode("utf-8"))

    def _create_run(self, run_id: str) -> str:
        run_root = self.runs_dir / run_id
        paths = build_run_paths(run_root)
        ensure_run_layout(paths)
        initialize_run_config(paths, model="sonnet", venue="neurips_2025")
        initialize_run_manifest(paths)
        write_text(paths.user_input, "HTTP run for studio service.")
        write_text(
            paths.logs,
            (
                "=== 2026-04-09T10:00:00 | run_start ===\n"
                "Run root\n\n"
                "=== 2026-04-09T10:00:01 | 01_literature_survey approved ===\n"
                "Approved\n\n"
                "=== 2026-04-09T10:00:02 | 05_experimentation attempt 2 user_choice ===\n"
                "Human review pending\n"
            ),
        )
        write_text(paths.literature_dir / "survey_notes.md", "# Survey\n\n- Core evidence.\n")
        write_text(paths.data_dir / "dataset_manifest.json", json.dumps({"dataset": "digits"}))
        write_text(paths.results_dir / "results.json", json.dumps({"accuracy": 0.91}))
        (paths.figures_dir / "accuracy.png").write_bytes(b"\x89PNG test figure")
        write_text(
            paths.writing_dir / "main.tex",
            "\\documentclass{article}\n\\begin{document}\n\\input{sections/intro}\n\\end{document}\n",
        )
        sections_dir = paths.writing_dir / "sections"
        sections_dir.mkdir(parents=True, exist_ok=True)
        write_text(sections_dir / "intro.tex", "\\section{Intro}\nStudio preview test.\n")
        write_text(paths.writing_dir / "build.log", "latexmk -pdf main.tex\nOutput written on main.pdf\n")
        (paths.artifacts_dir / "paper.pdf").write_bytes(b"%PDF-1.4 studio http test")
        write_artifact_index(paths)

        for stage in (STAGE_01, STAGE_02, STAGE_03, STAGE_04):
            write_text(paths.stage_file(stage), _stage_markdown(stage))
            mark_stage_approved_manifest(paths, stage, 1, [])

        write_text(paths.stage_file(STAGE_05), _stage_markdown(STAGE_05))
        mark_stage_human_review_manifest(paths, STAGE_05, 2, ["workspace/results/results.json"])
        return run_id


def _stage_markdown(stage) -> str:
    return (
        f"# Stage {stage.number:02d}: {stage.display_name}\n\n"
        "## Objective\n"
        "Test objective.\n\n"
        "## Previously Approved Stage Summaries\n"
        "_None yet._\n\n"
        "## What I Did\n"
        "Executed a test stage.\n\n"
        "## Key Results\n"
        "- Produced stable test artifacts.\n\n"
        "## Files Produced\n"
        "- `workspace/notes/test.md` - test artifact\n\n"
        "## Suggestions for Refinement\n"
        "1. Tighten scope.\n"
        "2. Strengthen evidence.\n"
        "3. Clarify risks.\n\n"
        "## Your Options\n"
        "1. Use suggestion 1\n"
        "2. Use suggestion 2\n"
        "3. Use suggestion 3\n"
        "4. Refine with your own feedback\n"
        "5. Approve and continue\n"
        "6. Abort\n"
    )


if __name__ == "__main__":
    unittest.main()
