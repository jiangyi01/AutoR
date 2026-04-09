from __future__ import annotations

import json
import re
from dataclasses import asdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from .artifact_index import ArtifactIndex, load_artifact_index
from .manifest import ensure_run_manifest, load_run_manifest
from .utils import STAGES, RunPaths, build_run_paths, read_text


IterationMode = Literal["continue", "redo", "branch"]
IterationScopeType = Literal["stage", "file", "subtree", "manuscript"]
ProjectMode = Literal["human", "autor"]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    normalized = normalized.strip("-")
    return normalized or "project"


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    title: str
    thesis: str
    default_mode: ProjectMode
    tags: list[str] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    active_run_id: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "thesis": self.thesis,
            "default_mode": self.default_mode,
            "tags": list(self.tags),
            "run_ids": list(self.run_ids),
            "active_run_id": self.active_run_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ProjectRecord":
        default_mode = str(payload.get("default_mode") or "human").strip().lower() or "human"
        if default_mode not in {"human", "autor"}:
            default_mode = "human"
        return cls(
            project_id=str(payload.get("project_id") or "").strip(),
            title=str(payload.get("title") or "").strip(),
            thesis=str(payload.get("thesis") or "").strip(),
            default_mode=default_mode,
            tags=[str(item).strip() for item in payload.get("tags", []) if str(item).strip()],
            run_ids=[str(item).strip() for item in payload.get("run_ids", []) if str(item).strip()],
            active_run_id=str(payload["active_run_id"]) if payload.get("active_run_id") is not None else None,
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )


@dataclass(frozen=True)
class StudioStageSummary:
    number: int
    slug: str
    title: str
    status: str
    approved: bool
    dirty: bool
    stale: bool
    attempt_count: int
    artifact_paths: list[str]
    updated_at: str
    approved_at: str | None = None


@dataclass(frozen=True)
class StudioRunSummary:
    run_id: str
    run_root: str
    goal: str
    model: str
    venue: str
    run_status: str
    current_stage_slug: str | None
    updated_at: str
    completed_at: str | None
    artifact_count: int
    counts_by_category: dict[str, int]
    stages: list[StudioStageSummary]


@dataclass(frozen=True)
class StudioProjectSummary:
    project_id: str
    title: str
    thesis: str
    default_mode: ProjectMode
    tags: list[str]
    run_ids: list[str]
    active_run_id: str | None
    latest_run_status: str | None
    latest_completed_stage_slug: str | None
    updated_at: str


@dataclass(frozen=True)
class FileTreeNode:
    name: str
    rel_path: str
    node_type: Literal["directory", "file"]
    size_bytes: int = 0
    children: list["FileTreeNode"] = field(default_factory=list)


@dataclass(frozen=True)
class IterationRequest:
    run_id: str
    base_stage_slug: str
    scope_type: IterationScopeType
    scope_value: str
    mode: IterationMode
    freeze_upstream: bool = True
    invalidate_downstream: bool = True
    user_feedback: str = ""


@dataclass(frozen=True)
class IterationPlan:
    run_id: str
    base_stage_slug: str
    scope_type: IterationScopeType
    scope_value: str
    mode: IterationMode
    preserved_stages: list[str]
    affected_stages: list[str]
    stale_stages: list[str]
    branch_run_id: str | None
    reuses_current_run: bool
    summary: str


class ProjectIndexStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._registry_path = self.root / "projects.json"

    def list_projects(self) -> list[ProjectRecord]:
        if not self._registry_path.exists():
            return []
        payload = json.loads(self._registry_path.read_text(encoding="utf-8"))
        return [
            ProjectRecord.from_dict(item)
            for item in payload.get("projects", [])
            if isinstance(item, dict)
        ]

    def create_project(
        self,
        title: str,
        thesis: str,
        default_mode: ProjectMode = "human",
        tags: list[str] | None = None,
    ) -> ProjectRecord:
        projects = self.list_projects()
        project_id = self._allocate_project_id(title, projects)
        record = ProjectRecord(
            project_id=project_id,
            title=title.strip(),
            thesis=thesis.strip(),
            default_mode=default_mode,
            tags=list(tags or []),
            run_ids=[],
            active_run_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        self._save_projects(projects + [record])
        return record

    def attach_run(self, project_id: str, run_id: str, make_active: bool = True) -> ProjectRecord:
        projects = self.list_projects()
        updated: list[ProjectRecord] = []
        selected: ProjectRecord | None = None
        for project in projects:
            if project.project_id != project_id:
                updated.append(project)
                continue
            run_ids = list(project.run_ids)
            if run_id not in run_ids:
                run_ids.append(run_id)
            selected = ProjectRecord(
                project_id=project.project_id,
                title=project.title,
                thesis=project.thesis,
                default_mode=project.default_mode,
                tags=project.tags,
                run_ids=run_ids,
                active_run_id=run_id if make_active else project.active_run_id,
                created_at=project.created_at,
                updated_at=_now(),
            )
            updated.append(selected)
        if selected is None:
            raise KeyError(f"Unknown project id: {project_id}")
        self._save_projects(updated)
        return selected

    def _allocate_project_id(self, title: str, existing: list[ProjectRecord]) -> str:
        base = _slugify(title)
        taken = {project.project_id for project in existing}
        candidate = base
        counter = 2
        while candidate in taken:
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def _save_projects(self, projects: list[ProjectRecord]) -> None:
        payload = {"projects": [project.to_dict() for project in projects]}
        self._registry_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )


class StudioService:
    def __init__(
        self,
        repo_root: Path,
        runs_dir: Path | None = None,
        metadata_root: Path | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.runs_dir = runs_dir or (repo_root / "runs")
        self.metadata_root = metadata_root or (repo_root / ".autor")
        self.project_store = ProjectIndexStore(self.metadata_root)

    def create_project(
        self,
        title: str,
        thesis: str,
        default_mode: ProjectMode = "human",
        tags: list[str] | None = None,
    ) -> ProjectRecord:
        return self.project_store.create_project(
            title=title,
            thesis=thesis,
            default_mode=default_mode,
            tags=tags,
        )

    def list_projects(self) -> list[ProjectRecord]:
        return self.project_store.list_projects()

    def list_project_summaries(self) -> list[StudioProjectSummary]:
        return [self.get_project_summary(project.project_id) for project in self.project_store.list_projects()]

    def get_project_summary(self, project_id: str) -> StudioProjectSummary:
        project = next((item for item in self.project_store.list_projects() if item.project_id == project_id), None)
        if project is None:
            raise KeyError(f"Unknown project id: {project_id}")

        run_id = project.active_run_id or (project.run_ids[-1] if project.run_ids else None)
        latest_run_status: str | None = None
        latest_completed_stage_slug: str | None = None
        if run_id is not None:
            run_summary = self.get_run_summary(run_id)
            latest_run_status = run_summary.run_status
            approved = [stage.slug for stage in run_summary.stages if stage.approved]
            latest_completed_stage_slug = approved[-1] if approved else None

        return StudioProjectSummary(
            project_id=project.project_id,
            title=project.title,
            thesis=project.thesis,
            default_mode=project.default_mode,
            tags=list(project.tags),
            run_ids=list(project.run_ids),
            active_run_id=project.active_run_id,
            latest_run_status=latest_run_status,
            latest_completed_stage_slug=latest_completed_stage_slug,
            updated_at=project.updated_at,
        )

    def attach_run_to_project(self, project_id: str, run_id: str, make_active: bool = True) -> ProjectRecord:
        self._require_run(run_id)
        return self.project_store.attach_run(project_id, run_id, make_active=make_active)

    def list_run_ids(self) -> list[str]:
        if not self.runs_dir.exists():
            return []
        run_ids = [
            path.name
            for path in self.runs_dir.iterdir()
            if path.is_dir() and (path / "run_manifest.json").exists()
        ]
        return sorted(run_ids)

    def get_run_summary(self, run_id: str) -> StudioRunSummary:
        paths = self._require_run(run_id)
        manifest = ensure_run_manifest(paths)
        config = self._load_json(paths.run_config)
        artifact_index = load_artifact_index(paths.artifact_index)
        goal = read_text(paths.user_input).strip() if paths.user_input.exists() else ""
        stages = [
            StudioStageSummary(
                number=entry.number,
                slug=entry.slug,
                title=entry.title,
                status=entry.status,
                approved=entry.approved,
                dirty=entry.dirty,
                stale=entry.stale,
                attempt_count=entry.attempt_count,
                artifact_paths=list(entry.artifact_paths),
                updated_at=entry.updated_at,
                approved_at=entry.approved_at,
            )
            for entry in manifest.stages
        ]
        counts_by_category = artifact_index.counts_by_category if artifact_index is not None else {}
        return StudioRunSummary(
            run_id=run_id,
            run_root=str(paths.run_root),
            goal=goal,
            model=str(config.get("model") or "unknown"),
            venue=str(config.get("venue") or "default"),
            run_status=manifest.run_status,
            current_stage_slug=manifest.current_stage_slug,
            updated_at=manifest.updated_at,
            completed_at=manifest.completed_at,
            artifact_count=artifact_index.artifact_count if artifact_index is not None else 0,
            counts_by_category=counts_by_category,
            stages=stages,
        )

    def get_stage_document(self, run_id: str, stage_slug: str) -> str:
        paths = self._require_run(run_id)
        stage = _resolve_stage(stage_slug)
        return read_text(paths.stage_file(stage))

    def get_artifact_index(self, run_id: str) -> ArtifactIndex | None:
        paths = self._require_run(run_id)
        return load_artifact_index(paths.artifact_index)

    def get_file_content(self, run_id: str, relative_path: str) -> dict[str, object]:
        paths = self._require_run(run_id)
        path = self._resolve_run_relative_path(paths, relative_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Unknown run file: {relative_path}")
        run_root = paths.run_root.resolve()
        try:
            content = path.read_text(encoding="utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            content = ""
            encoding = "binary"
        return {
            "run_id": run_id,
            "relative_path": str(path.resolve().relative_to(run_root)).replace("\\", "/"),
            "size_bytes": path.stat().st_size,
            "encoding": encoding,
            "content": content,
        }

    def build_file_tree(
        self,
        run_id: str,
        root_relative: str = "workspace",
        max_depth: int | None = None,
        include_hidden: bool = False,
    ) -> FileTreeNode:
        paths = self._require_run(run_id)
        root_path = paths.run_root / root_relative
        if not root_path.exists():
            raise FileNotFoundError(f"Unknown run path: {root_relative}")
        return self._build_tree_node(
            base_root=paths.run_root,
            path=root_path,
            max_depth=max_depth,
            include_hidden=include_hidden,
        )

    def plan_iteration(self, request: IterationRequest) -> IterationPlan:
        run = self.get_run_summary(request.run_id)
        stage = _resolve_stage(request.base_stage_slug)
        preserved_stages = [
            item.slug
            for item in run.stages
            if request.freeze_upstream and item.number < stage.number
        ]
        affected_stages = _affected_stage_slugs(stage.slug, request.scope_type)
        stale_stages: list[str] = []
        branch_run_id: str | None = None
        reuses_current_run = request.mode != "branch"

        if request.mode == "continue":
            affected_stages = [stage.slug]
            stale_stages = []
            summary = (
                f"Continue {stage.slug} in the current run. "
                f"Only the selected scope `{request.scope_value}` is expected to change."
            )
        elif request.mode == "redo":
            if request.invalidate_downstream:
                stale_stages = [
                    item.slug
                    for item in run.stages
                    if item.number > stage.number and (item.approved or item.status != "pending")
                ]
            summary = (
                f"Redo the current run from {stage.slug}. "
                f"Downstream stages marked stale: {', '.join(stale_stages) if stale_stages else 'none'}."
            )
        else:
            branch_run_id = f"{run.run_id}-branch-{stage.slug}"
            stale_stages = []
            summary = (
                f"Create a new branch run from {stage.slug} for scope `{request.scope_value}`. "
                f"The current run stays unchanged."
            )

        return IterationPlan(
            run_id=request.run_id,
            base_stage_slug=stage.slug,
            scope_type=request.scope_type,
            scope_value=request.scope_value,
            mode=request.mode,
            preserved_stages=preserved_stages,
            affected_stages=affected_stages,
            stale_stages=stale_stages,
            branch_run_id=branch_run_id,
            reuses_current_run=reuses_current_run,
            summary=summary,
        )

    def _require_run(self, run_id: str) -> RunPaths:
        run_root = self.runs_dir / run_id
        manifest = load_run_manifest(run_root / "run_manifest.json")
        if manifest is None:
            raise FileNotFoundError(f"Run not found: {run_id}")
        return build_run_paths(run_root)

    def _build_tree_node(
        self,
        base_root: Path,
        path: Path,
        max_depth: int | None,
        include_hidden: bool,
        depth: int = 0,
    ) -> FileTreeNode:
        rel_path = str(path.relative_to(base_root)).replace("\\", "/")
        if path.is_file():
            return FileTreeNode(
                name=path.name,
                rel_path=rel_path,
                node_type="file",
                size_bytes=path.stat().st_size,
            )

        if max_depth is not None and depth >= max_depth:
            return FileTreeNode(name=path.name, rel_path=rel_path, node_type="directory", children=[])

        children: list[FileTreeNode] = []
        for child in sorted(path.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
            if not include_hidden and child.name.startswith("."):
                continue
            children.append(
                self._build_tree_node(
                    base_root=base_root,
                    path=child,
                    max_depth=max_depth,
                    include_hidden=include_hidden,
                    depth=depth + 1,
                )
            )
        return FileTreeNode(name=path.name, rel_path=rel_path, node_type="directory", children=children)

    def _load_json(self, path: Path) -> dict[str, object]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _resolve_run_relative_path(self, paths: RunPaths, relative_path: str) -> Path:
        candidate = (paths.run_root / relative_path).resolve()
        run_root = paths.run_root.resolve()
        try:
            candidate.relative_to(run_root)
        except ValueError as exc:
            raise ValueError(f"Path escapes run root: {relative_path}") from exc
        return candidate


def _resolve_stage(stage_slug: str):
    for stage in STAGES:
        if stage.slug == stage_slug:
            return stage
    raise KeyError(f"Unknown stage slug: {stage_slug}")


def _affected_stage_slugs(base_stage_slug: str, scope_type: IterationScopeType) -> list[str]:
    base_stage = _resolve_stage(base_stage_slug)
    if scope_type == "stage":
        return [stage.slug for stage in STAGES if stage.number >= base_stage.number]
    if scope_type in {"file", "subtree", "manuscript"}:
        return [stage.slug for stage in STAGES if stage.number >= base_stage.number]
    return [base_stage.slug]


def studio_to_dict(value):
    if isinstance(value, ArtifactIndex):
        return value.to_dict()
    return asdict(value)
