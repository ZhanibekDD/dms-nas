"""
Одиночный прогон extraction pipeline по EmployeeDocument.

  python manage.py extract_pass_doc --id 123
  python manage.py extract_pass_doc --source-path "C:\\path\\to\\file.pdf"
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from pass_docs.models import EmployeeDocument
from pass_docs.services.document_pipeline import run_extraction


class Command(BaseCommand):
    help = "Прогнать vision/extraction pipeline для одного EmployeeDocument."

    def add_arguments(self, parser):
        g = parser.add_mutually_exclusive_group(required=True)
        g.add_argument("--id", type=int, help="PK EmployeeDocument")
        g.add_argument(
            "--source-path",
            dest="source_path",
            type=str,
            help="Точный source_path записи (как в БД)",
        )

    def handle(self, *args, **options):
        doc = self._resolve_document(options)
        self.stdout.write(
            self.style.NOTICE(
                f"Документ id={doc.pk} type={doc.document_type.code} path={doc.source_path}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "Если пойдёт запрос к Ollama (vision), ответ может занять несколько минут — "
                "не прерывайте без нужды (таймаут чтения по умолчанию 900 с, см. OLLAMA_READ_TIMEOUT)."
            )
        )
        summary = run_extraction(doc)
        doc.refresh_from_db()
        self.stdout.write(self.style.SUCCESS("Готово."))
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
        self.stdout.write("--- extracted_json ---")
        self.stdout.write(json.dumps(doc.extracted_json, ensure_ascii=False, indent=2))

    def _resolve_document(self, options: dict) -> EmployeeDocument:
        if options.get("id"):
            try:
                return EmployeeDocument.objects.select_related("document_type").get(
                    pk=options["id"]
                )
            except EmployeeDocument.DoesNotExist as exc:
                raise CommandError(f"EmployeeDocument id={options['id']} не найден") from exc

        raw = (options.get("source_path") or "").strip()
        if not raw:
            raise CommandError("Пустой --source-path")

        resolved = str(Path(raw).resolve())
        doc = (
            EmployeeDocument.objects.select_related("document_type")
            .filter(source_path=resolved)
            .order_by("-id")
            .first()
        )
        if doc:
            return doc
        doc = (
            EmployeeDocument.objects.select_related("document_type")
            .filter(source_path=raw)
            .order_by("-id")
            .first()
        )
        if doc:
            return doc
        raise CommandError(
            f"EmployeeDocument с source_path не найден: {raw!r} (resolve: {resolved!r})"
        )
