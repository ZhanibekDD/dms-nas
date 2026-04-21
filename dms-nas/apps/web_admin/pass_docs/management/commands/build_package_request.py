"""
Сборка артефактов (Excel + ZIP) для PackageRequest.

  python manage.py build_package_request --id 123
  python manage.py build_package_request --id 123 --allow-draft
  python manage.py build_package_request --id 123 --allow-ready
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from pass_docs.services.package_builder import PackageBuildError, build_package_for_request


class Command(BaseCommand):
    help = "Собрать XLSX и ZIP для PackageRequest (статус submitted или draft с флагом)."

    def add_arguments(self, parser):
        parser.add_argument("--id", type=int, required=True, help="PK PackageRequest")
        parser.add_argument(
            "--allow-draft",
            action="store_true",
            help="Разрешить сборку из статуса draft (для отладки).",
        )
        parser.add_argument(
            "--allow-ready",
            action="store_true",
            help="Разрешить пересборку из статуса ready (обновить Excel/ZIP).",
        )

    def handle(self, *args, **options):
        rid = options["id"]
        allow_draft = bool(options["allow_draft"])
        allow_ready = bool(options["allow_ready"])
        try:
            summary = build_package_for_request(
                rid, allow_draft=allow_draft, allow_ready=allow_ready
            )
        except PackageBuildError as exc:
            raise CommandError(str(exc)) from exc

        if summary.get("ok"):
            self.stdout.write(self.style.SUCCESS(json.dumps(summary, ensure_ascii=False, indent=2)))
        else:
            self.stdout.write(self.style.ERROR(json.dumps(summary, ensure_ascii=False, indent=2)))
            raise CommandError(summary.get("last_error") or "Сборка завершилась с ошибкой.")
