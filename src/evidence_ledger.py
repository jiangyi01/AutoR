from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .utils import RunPaths


def literature_sources_path(paths: "RunPaths") -> Path:
    return paths.literature_dir / "sources.json"


def literature_claims_path(paths: "RunPaths") -> Path:
    return paths.literature_dir / "claims.json"


def validate_literature_evidence(paths: "RunPaths") -> list[str]:
    problems: list[str] = []
    sources_payload = _load_json_payload(literature_sources_path(paths), "sources.json", problems)
    claims_payload = _load_json_payload(literature_claims_path(paths), "claims.json", problems)

    if sources_payload is None or claims_payload is None:
        return problems

    sources = _extract_entries(sources_payload, "sources", "sources.json", problems)
    claims = _extract_entries(claims_payload, "claims", "claims.json", problems)

    source_ids: set[str] = set()
    for index, entry in enumerate(sources, start=1):
        if not isinstance(entry, dict):
            problems.append(f"sources.json entry {index} must be an object.")
            continue
        source_id = _clean_str(entry.get("source_id"))
        if not source_id:
            problems.append(f"sources.json entry {index} is missing a non-empty source_id.")
            continue
        if source_id in source_ids:
            problems.append(f"sources.json contains duplicate source_id '{source_id}'.")
        source_ids.add(source_id)
        if not _clean_str(entry.get("title")):
            problems.append(f"sources.json entry {index} is missing a non-empty title.")

    for index, entry in enumerate(claims, start=1):
        if not isinstance(entry, dict):
            problems.append(f"claims.json entry {index} must be an object.")
            continue
        claim_id = _clean_str(entry.get("claim_id"))
        if not claim_id:
            problems.append(f"claims.json entry {index} is missing a non-empty claim_id.")
        if not _clean_str(entry.get("statement")):
            problems.append(f"claims.json entry {index} is missing a non-empty statement.")
        referenced_ids = _nonempty_string_list(entry.get("source_ids"))
        if not referenced_ids:
            problems.append(f"claims.json entry {index} must include at least one source_id.")
            continue
        unknown_ids = sorted(source_id for source_id in referenced_ids if source_id not in source_ids)
        if unknown_ids:
            problems.append(
                f"claims.json entry {index} references unknown source_ids: {', '.join(unknown_ids)}."
            )

    return problems


def validate_citation_verification(path: Path) -> list[str]:
    problems: list[str] = []
    payload = _load_json_payload(path, "citation_verification.json", problems)
    if not isinstance(payload, dict):
        return problems

    if not _clean_str(payload.get("overall_status")):
        problems.append("citation_verification.json is missing a non-empty overall_status.")

    total_citations = payload.get("total_citations")
    if not isinstance(total_citations, int) or isinstance(total_citations, bool) or total_citations < 0:
        problems.append("citation_verification.json must include a non-negative integer total_citations.")

    claim_coverage = payload.get("claim_coverage")
    if not isinstance(claim_coverage, list) or not claim_coverage:
        problems.append("citation_verification.json must include a non-empty claim_coverage list.")
        return problems

    for index, entry in enumerate(claim_coverage, start=1):
        if not isinstance(entry, dict):
            problems.append(f"citation_verification.json claim_coverage entry {index} must be an object.")
            continue
        if not _clean_str(entry.get("claim")):
            problems.append(
                f"citation_verification.json claim_coverage entry {index} is missing a non-empty claim."
            )
        citation_keys = _nonempty_string_list(entry.get("citation_keys"))
        source_ids = _nonempty_string_list(entry.get("source_ids"))
        if not citation_keys and not source_ids:
            problems.append(
                "citation_verification.json claim_coverage entry "
                f"{index} must include citation_keys or source_ids."
            )

    return problems


def _load_json_payload(path: Path, label: str, problems: list[str]) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        problems.append(f"Missing {label}.")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        problems.append(f"{label} is not valid JSON: {exc.msg}.")
        return None
    if not isinstance(payload, (dict, list)):
        problems.append(f"{label} must be a JSON object or list.")
        return None
    return payload


def _extract_entries(
    payload: dict[str, Any] | list[Any],
    key: str,
    label: str,
    problems: list[str],
) -> list[Any]:
    entries: Any = payload
    if isinstance(payload, dict):
        entries = payload.get(key)
    if not isinstance(entries, list) or not entries:
        problems.append(f"{label} must contain a non-empty '{key}' list.")
        return []
    return entries


def _clean_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _nonempty_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = [_clean_str(item) for item in value]
    return [item for item in cleaned if item]
