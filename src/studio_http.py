from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from mimetypes import guess_type
from urllib.parse import parse_qs, urlparse

from .studio_service import IterationRequest, StudioService, studio_to_dict


def build_handler(service: StudioService, static_root: Path):
    class StudioHandler(BaseHTTPRequestHandler):
        server_version = "AutoRStudioHTTP/0.1"

        def do_GET(self) -> None:
            try:
                self._dispatch_get()
            except FileNotFoundError as exc:
                self._write_error(HTTPStatus.NOT_FOUND, str(exc))
            except KeyError as exc:
                self._write_error(HTTPStatus.NOT_FOUND, str(exc))
            except ValueError as exc:
                self._write_error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:  # pragma: no cover - defensive
                self._write_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def do_POST(self) -> None:
            try:
                self._dispatch_post()
            except FileNotFoundError as exc:
                self._write_error(HTTPStatus.NOT_FOUND, str(exc))
            except KeyError as exc:
                self._write_error(HTTPStatus.NOT_FOUND, str(exc))
            except ValueError as exc:
                self._write_error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:  # pragma: no cover - defensive
                self._write_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _dispatch_get(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            parts = [item for item in path.split("/") if item]

            if path in {"/", "/studio", "/studio/"}:
                self._serve_static_file(static_root / "index.html")
                return

            if path.startswith("/studio/"):
                relative = path[len("/studio/") :]
                self._serve_static_file(static_root / relative)
                return

            if path == "/healthz":
                self._write_json(HTTPStatus.OK, {"status": "ok"})
                return

            if parts == ["api", "projects"]:
                payload = {"projects": [studio_to_dict(item) for item in service.list_projects()]}
                self._write_json(HTTPStatus.OK, payload)
                return

            if parts == ["api", "projects", "overview"]:
                payload = {"projects": [studio_to_dict(item) for item in service.list_project_summaries()]}
                self._write_json(HTTPStatus.OK, payload)
                return

            if len(parts) == 3 and parts[:2] == ["api", "projects"]:
                payload = studio_to_dict(service.get_project_summary(parts[2]))
                self._write_json(HTTPStatus.OK, payload)
                return

            if parts == ["api", "runs"]:
                self._write_json(HTTPStatus.OK, {"run_ids": service.list_run_ids()})
                return

            if len(parts) == 3 and parts[:2] == ["api", "runs"]:
                summary = service.get_run_summary(parts[2])
                self._write_json(HTTPStatus.OK, studio_to_dict(summary))
                return

            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "paper":
                preview = service.get_paper_preview(parts[2])
                self._write_json(HTTPStatus.OK, studio_to_dict(preview))
                return

            if len(parts) == 5 and parts[:2] == ["api", "runs"] and parts[3:5] == ["paper", "pdf"]:
                body = service.get_paper_pdf_bytes(parts[2])
                self._write_bytes(HTTPStatus.OK, body, content_type="application/pdf")
                return

            if len(parts) == 5 and parts[:2] == ["api", "runs"] and parts[3] == "stages":
                markdown = service.get_stage_document(parts[2], parts[4])
                self._write_json(
                    HTTPStatus.OK,
                    {"run_id": parts[2], "stage_slug": parts[4], "markdown": markdown},
                )
                return

            if len(parts) == 5 and parts[:2] == ["api", "runs"] and parts[3:5] == ["files", "tree"]:
                root_relative = query.get("root", ["workspace"])[0]
                max_depth = query.get("depth", [None])[0]
                tree = service.build_file_tree(
                    parts[2],
                    root_relative=root_relative,
                    max_depth=int(max_depth) if max_depth is not None else None,
                )
                self._write_json(HTTPStatus.OK, studio_to_dict(tree))
                return

            if len(parts) == 5 and parts[:2] == ["api", "runs"] and parts[3:5] == ["files", "content"]:
                relative_path = query.get("path", [""])[0]
                payload = service.get_file_content(parts[2], relative_path)
                self._write_json(HTTPStatus.OK, payload)
                return

            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "artifacts":
                artifact_index = service.get_artifact_index(parts[2])
                payload = artifact_index.to_dict() if artifact_index is not None else {}
                self._write_json(HTTPStatus.OK, payload)
                return

            raise FileNotFoundError(f"Unknown route: {path}")

        def _dispatch_post(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            parts = [item for item in path.split("/") if item]
            payload = self._read_json_body()

            if parts == ["api", "projects"]:
                project = service.create_project(
                    title=str(payload.get("title") or "").strip(),
                    thesis=str(payload.get("thesis") or "").strip(),
                    default_mode=str(payload.get("default_mode") or "human").strip().lower() or "human",
                    tags=[
                        str(item).strip()
                        for item in payload.get("tags", [])
                        if str(item).strip()
                    ],
                )
                self._write_json(HTTPStatus.CREATED, studio_to_dict(project))
                return

            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "runs":
                project = service.attach_run_to_project(
                    parts[2],
                    run_id=str(payload.get("run_id") or "").strip(),
                    make_active=bool(payload.get("make_active", True)),
                )
                self._write_json(HTTPStatus.OK, studio_to_dict(project))
                return

            if len(parts) == 5 and parts[:2] == ["api", "runs"] and parts[3:5] == ["iterations", "plan"]:
                plan = service.plan_iteration(
                    IterationRequest(
                        run_id=parts[2],
                        base_stage_slug=str(payload.get("base_stage_slug") or "").strip(),
                        scope_type=str(payload.get("scope_type") or "stage").strip(),
                        scope_value=str(payload.get("scope_value") or "").strip(),
                        mode=str(payload.get("mode") or "continue").strip(),
                        freeze_upstream=bool(payload.get("freeze_upstream", True)),
                        invalidate_downstream=bool(payload.get("invalidate_downstream", True)),
                        user_feedback=str(payload.get("user_feedback") or "").strip(),
                    )
                )
                self._write_json(HTTPStatus.OK, studio_to_dict(plan))
                return

            raise FileNotFoundError(f"Unknown route: {path}")

        def _read_json_body(self) -> dict[str, object]:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                return {}
            body = self.rfile.read(content_length).decode("utf-8")
            if not body.strip():
                return {}
            return json.loads(body)

        def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
            body = json.dumps(payload, indent=2, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _write_error(self, status: HTTPStatus, detail: str) -> None:
            self._write_json(status, {"error": detail})

        def _write_bytes(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_static_file(self, path: Path) -> None:
            candidate = path.resolve()
            root = static_root.resolve()
            try:
                candidate.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"Static path escapes root: {path}") from exc
            if not candidate.exists() or not candidate.is_file():
                raise FileNotFoundError(f"Static asset not found: {candidate.name}")
            mime_type = guess_type(candidate.name)[0] or "application/octet-stream"
            body = candidate.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{mime_type}; charset=utf-8" if mime_type.startswith("text/") else mime_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return StudioHandler


def create_server(
    repo_root: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    runs_dir: Path | None = None,
    metadata_root: Path | None = None,
) -> ThreadingHTTPServer:
    service = StudioService(
        repo_root=repo_root,
        runs_dir=runs_dir,
        metadata_root=metadata_root,
    )
    static_root = repo_root / "studio_web"
    if not static_root.exists():
        static_root = Path(__file__).resolve().parent.parent / "studio_web"
    handler = build_handler(service, static_root=static_root)
    return ThreadingHTTPServer((host, port), handler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AutoR Studio local HTTP service")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8000, help="Bind port.")
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--runs-dir", help="Override runs directory.")
    parser.add_argument("--metadata-root", help="Override metadata root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    runs_dir = Path(args.runs_dir).resolve() if args.runs_dir else None
    metadata_root = Path(args.metadata_root).resolve() if args.metadata_root else None
    server = create_server(
        repo_root=repo_root,
        host=args.host,
        port=args.port,
        runs_dir=runs_dir,
        metadata_root=metadata_root,
    )
    print(f"AutoR Studio service listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
