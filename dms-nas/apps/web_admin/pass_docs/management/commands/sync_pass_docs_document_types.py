"""
Выравнивание DocumentType по каталогу DOCUMENT_CODE_CATALOG.

  python manage.py sync_pass_docs_document_types          # только отчёт
  python manage.py sync_pass_docs_document_types --apply  # записать в БД

Не трогает UI, package builder, extraction, email.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from pass_docs.catalog.document_type_sync import (
    classify_document_type,
    planned_field_updates,
    preview_sync,
)
from pass_docs.catalog.document_codes import get_catalog_entry
from pass_docs.models import DocumentType


class Command(BaseCommand):
    help = "Синхронизация name / extractor_kind у DocumentType с каталогом pass_docs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Записать изменения в БД (по умолчанию только отчёт).",
        )

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        cleaned_codes: list[str] = []
        uncertain: list[str] = []
        previews: list[str] = []

        qs = DocumentType.objects.all().order_by("code")

        def _process():
            for dt in qs:
                st = classify_document_type(dt)
                if st == "uncertain":
                    uncertain.append(dt.code)
                    continue
                if st != "would_update":
                    continue
                cat = get_catalog_entry(dt.code or "")
                updates = planned_field_updates(dt, cat)
                if not updates:
                    continue
                pv = preview_sync(dt, updates)
                if pv:
                    parts = [f"code={pv.code!r}"]
                    if pv.new_name is not None:
                        parts.append(f"name: {pv.old_name!r} -> {pv.new_name!r}")
                    if pv.new_extractor_kind is not None:
                        parts.append(
                            f"extractor_kind: {pv.old_extractor_kind!r} -> {pv.new_extractor_kind!r}"
                        )
                    previews.append("  " + "; ".join(parts))
                if apply:
                    if "name" in updates:
                        dt.name = updates["name"]
                    if "extractor_kind" in updates:
                        dt.extractor_kind = updates["extractor_kind"]
                    dt.save(update_fields=list(updates.keys()))
                cleaned_codes.append(dt.code)

        if apply:
            with transaction.atomic():
                _process()
        else:
            _process()

        self.stdout.write(self.style.NOTICE("=== pass_docs: синхронизация DocumentType с каталогом ==="))
        if apply:
            self.stdout.write(self.style.WARNING("Режим --apply: изменения записаны в БД."))
        else:
            self.stdout.write(self.style.WARNING("Без --apply: только отчёт (БД не менялась)."))

        if previews:
            self.stdout.write(self.style.NOTICE("Изменения (план):"))
            for line in previews:
                self.stdout.write(line)

        self.stdout.write("")
        label = "Дочищено кодов" if apply else "Кандидатов на обновление по каталогу"
        self.stdout.write(self.style.SUCCESS(f"{label}: {len(cleaned_codes)}"))
        if cleaned_codes:
            self.stdout.write("  " + ", ".join(sorted(cleaned_codes, key=str.lower)))

        self.stdout.write("")
        self.stdout.write(self.style.WARNING(f"Uncertain (нет в каталоге, сырое имя или пустой extractor): {len(uncertain)}"))
        if uncertain:
            self.stdout.write("  " + ", ".join(sorted(uncertain, key=str.lower)))
