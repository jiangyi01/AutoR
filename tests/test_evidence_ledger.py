from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.evidence_ledger import (
    literature_claims_path,
    literature_sources_path,
    validate_citation_verification,
)
from src.utils import STAGES, build_run_paths, ensure_run_layout, validate_stage_artifacts


STAGE_01 = next(stage for stage in STAGES if stage.slug == "01_literature_survey")


class EvidenceLedgerTests(unittest.TestCase):
    def _build_paths(self) -> object:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        run_root = Path(tmp_dir.name) / "run"
        paths = build_run_paths(run_root)
        ensure_run_layout(paths)
        return paths

    def test_stage01_validation_accepts_traceable_source_and_claim_ledgers(self) -> None:
        paths = self._build_paths()
        literature_sources_path(paths).write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "source_id": "S1",
                            "title": "A traced source",
                            "citation": "Author et al. (2025)",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        literature_claims_path(paths).write_text(
            json.dumps(
                {
                    "claims": [
                        {
                            "claim_id": "CL1",
                            "statement": "The field still lacks a robust baseline.",
                            "source_ids": ["S1"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(validate_stage_artifacts(STAGE_01, paths), [])

    def test_stage01_validation_rejects_claims_with_unknown_sources(self) -> None:
        paths = self._build_paths()
        literature_sources_path(paths).write_text(
            json.dumps({"sources": [{"source_id": "S1", "title": "Known source"}]}),
            encoding="utf-8",
        )
        literature_claims_path(paths).write_text(
            json.dumps(
                {
                    "claims": [
                        {
                            "claim_id": "CL1",
                            "statement": "This claim references a missing source.",
                            "source_ids": ["S9"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        problems = validate_stage_artifacts(STAGE_01, paths)
        self.assertTrue(any("unknown source_ids" in problem for problem in problems))

    def test_citation_verification_requires_claim_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "citation_verification.json"
            path.write_text(
                json.dumps({"overall_status": "pass", "total_citations": 3}),
                encoding="utf-8",
            )

            problems = validate_citation_verification(path)
            self.assertTrue(any("claim_coverage" in problem for problem in problems))

    def test_citation_verification_accepts_claim_coverage_with_citation_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "citation_verification.json"
            path.write_text(
                json.dumps(
                    {
                        "overall_status": "pass",
                        "total_citations": 3,
                        "claim_coverage": [
                            {
                                "claim": "The benchmark result is supported.",
                                "citation_keys": ["smith2025"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(validate_citation_verification(path), [])


if __name__ == "__main__":
    unittest.main()
