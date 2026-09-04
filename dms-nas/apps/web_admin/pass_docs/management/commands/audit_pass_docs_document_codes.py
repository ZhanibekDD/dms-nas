"""Read-only audit for missing/mismatched Pass Docs filename codes."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from pass_docs.catalog.document_filenames import (
    MISSING_DOCUMENT_CODE,
    canonical_document_filename,
    parse_document_filename,
)
from pass_docs.models import EmployeeDocument


class Command(BaseCommand):
    help = (
        "Read-only audit of <code>&<name> filename markers. "
        "Never renames files and never writes to the database."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--details",
            action="store_true",
            help="Print document IDs and code statuses (no employee names or paths).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print a machine-readable JSON report.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Include documents where is_actual=false.",
        )

    def handle(self, *args, **options):
        qs = EmployeeDocument.objects.select_related("document_type").order_by("pk")
        if not options["include_inactive"]:
            qs = qs.filter(is_actual=True)

        report = {
            "mode": "read_only",
            "total": 0,
            "coded": 0,
            "inferred": 0,
            "missing": 0,
            "mismatch": 0,
            "unknown_type": 0,
            "details": [],
        }

        for doc in qs.iterator():
            stored_name = ""
            if doc.original_file:
                stored_name = doc.original_file.name or ""
            source_name = Path(stored_name or doc.source_path or "").name
            parsed = parse_document_filename(source_name)
            expected_code = (doc.document_type.code or MISSING_DOCUMENT_CODE).strip()
            status = parsed.status

            report["total"] += 1
            if expected_code == MISSING_DOCUMENT_CODE:
                report["unknown_type"] += 1
            if status == "missing":
                report["missing"] += 1
            elif status == "inferred":
                report["inferred"] += 1
            else:
                report["coded"] += 1

            mismatch = (
                status == "coded"
                and expected_code != MISSING_DOCUMENT_CODE
                and parsed.code != expected_code
            )
            if mismatch:
                report["mismatch"] += 1

            if options["details"] and (
                status != "coded"
                or mismatch
                or expected_code == MISSING_DOCUMENT_CODE
            ):
                report["details"].append(
                    {
                        "document_id": doc.pk,
                        "stored_code": parsed.code,
                        "expected_code": expected_code,
                        "status": status,
                        "mismatch": mismatch,
                        "canonical_filename": canonical_document_filename(
                            expected_code, source_name
                        ),
                    }
                )

        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return

        self.stdout.write(self.style.NOTICE("=== Pass Docs filename code audit ==="))
        self.stdout.write("mode: read_only")
        for key in (
            "total",
            "coded",
            "inferred",
            "missing",
            "mismatch",
            "unknown_type",
        ):
            self.stdout.write(f"{key}: {report[key]}")
        if options["details"]:
            for item in report["details"]:
                self.stdout.write(
                    "document_id={document_id} status={status} "
                    "stored={stored_code} expected={expected_code} "
                    "mismatch={mismatch} canonical={canonical_filename}".format(
                        **item
                    )
                )
