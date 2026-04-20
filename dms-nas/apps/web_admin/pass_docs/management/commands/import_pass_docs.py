"""
Импорт справочников и сотрудников из JSON (этап без vision/builder).

Ожидаемый формат файла (UTF-8):

{
  "document_types": [
    {"code": "passport_rf", "name": "Паспорт РФ", "description": "", "sort_order": 10}
  ],
  "profession_requirements": [
    {
      "profession_key": "builder",
      "profession_label": "Монтажник",
      "document_type_code": "passport_rf",
      "is_required": true,
      "notes": ""
    }
  ],
  "employees": [
    {
      "employee_code": "E-001",
      "full_name": "Иванов Иван Иванович",
      "profession_key": "builder",
      "profession_label": "Монтажник",
      "notes": "",
      "documents": [
        {
          "document_type_code": "passport_rf",
          "status": "ok",
          "external_reference": "4510 123456",
          "valid_until": "2030-12-31",
          "metadata": {}
        }
      ]
    }
  ]
}

Поля document_types / profession_requirements / employees могут быть пустыми или отсутствовать.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date

from pass_docs.models import (
    DocumentType,
    Employee,
    EmployeeDocument,
    ProfessionRequirement,
)


def _parse_date(value: Any):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return parse_date(value[:10])
    return None


class Command(BaseCommand):
    help = "Импорт pass_docs из JSON (типы, требования, сотрудники и их документы)."

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            type=str,
            help="Путь к JSON-файлу с данными для импорта",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать, что было бы импортировано, без записи в БД",
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"Файл не найден: {path}")

        try:
            raw = path.read_text(encoding="utf-8-sig")
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Некорректный JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise CommandError("Корень JSON должен быть объектом { ... }")

        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("Режим dry-run: транзакция будет откатана."))

        with transaction.atomic():
            stats = self._import_payload(data)
            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS("Импорт завершён."))
        for key, val in stats.items():
            self.stdout.write(f"  {key}: {val}")

    def _import_payload(self, data: dict) -> dict[str, int]:
        stats = {
            "document_types": 0,
            "profession_requirements": 0,
            "employees": 0,
            "employee_documents": 0,
        }

        for row in data.get("document_types") or []:
            if not isinstance(row, dict) or not row.get("code") or not row.get("name"):
                continue
            DocumentType.objects.update_or_create(
                code=str(row["code"]).strip(),
                defaults={
                    "name": str(row["name"]).strip(),
                    "description": str(row.get("description") or "").strip(),
                    "sort_order": int(row.get("sort_order") or 0),
                },
            )
            stats["document_types"] += 1

        for row in data.get("profession_requirements") or []:
            if not isinstance(row, dict):
                continue
            code = str(row.get("document_type_code") or "").strip()
            pkey = str(row.get("profession_key") or "").strip()
            if not code or not pkey:
                continue
            try:
                dt = DocumentType.objects.get(code=code)
            except DocumentType.DoesNotExist:
                self.stderr.write(
                    self.style.WARNING(
                        f"Пропуск требования: нет типа документа «{code}» (profession_key={pkey})"
                    )
                )
                continue
            ProfessionRequirement.objects.update_or_create(
                profession_key=pkey,
                document_type=dt,
                defaults={
                    "profession_label": str(row.get("profession_label") or "").strip(),
                    "is_required": bool(row.get("is_required", True)),
                    "notes": str(row.get("notes") or "").strip(),
                },
            )
            stats["profession_requirements"] += 1

        for row in data.get("employees") or []:
            if not isinstance(row, dict):
                continue
            ecode = str(row.get("employee_code") or "").strip()
            full_name = str(row.get("full_name") or "").strip()
            pkey = str(row.get("profession_key") or "").strip()
            if not ecode or not full_name or not pkey:
                self.stderr.write(self.style.WARNING("Пропуск сотрудника: нужны employee_code, full_name, profession_key"))
                continue
            emp, _created = Employee.objects.update_or_create(
                employee_code=ecode,
                defaults={
                    "full_name": full_name,
                    "profession_key": pkey,
                    "profession_label": str(row.get("profession_label") or "").strip(),
                    "notes": str(row.get("notes") or "").strip(),
                },
            )
            stats["employees"] += 1

            for doc_row in row.get("documents") or []:
                if not isinstance(doc_row, dict):
                    continue
                dcode = str(doc_row.get("document_type_code") or "").strip()
                if not dcode:
                    continue
                try:
                    dt = DocumentType.objects.get(code=dcode)
                except DocumentType.DoesNotExist:
                    self.stderr.write(
                        self.style.WARNING(
                            f"Пропуск документа сотрудника {ecode}: нет типа «{dcode}»"
                        )
                    )
                    continue
                status = str(doc_row.get("status") or EmployeeDocument.Status.PENDING).strip()
                allowed = {c for c, _ in EmployeeDocument.Status.choices}
                if status not in allowed:
                    status = EmployeeDocument.Status.PENDING
                meta = doc_row.get("metadata")
                if meta is None or not isinstance(meta, dict):
                    meta = {}
                EmployeeDocument.objects.update_or_create(
                    employee=emp,
                    document_type=dt,
                    defaults={
                        "status": status,
                        "external_reference": str(doc_row.get("external_reference") or "").strip(),
                        "valid_until": _parse_date(doc_row.get("valid_until")),
                        "metadata": meta,
                    },
                )
                stats["employee_documents"] += 1

        return stats
