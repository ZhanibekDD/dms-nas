"""
Импорт из папочной структуры документов (без JSON и без vision/builder).

Ожидается корень вида:
  python manage.py import_pass_docs --root "/path/to/Документы/PDF"

Подкаталоги сотрудников: полное имя папки «{prefix}&{подпись}», например «1&Гусев», «1&Гезик».
Уникальность сотрудника при импорте — по полному имени папки (import_key / source_folder_name),
а не по числу до «&»: префикс «1» может повторяться у разных людей.

Общие каталоги: «R&…» и «D&…» — документы организации; записи привязываются к
служебному сотруднику с import_key __COMMON_ORG__, в metadata фиксируется вид папки.

Файлы: код типа документа — подстрока до первого «&» в имени файла, например
  PASSPORT_RF&скан.pdf  →  тип PASSPORT_RF
Поддерживаются все файлы с «&» в имени (PDF, JPG, PNG и т.д.).

Повторный запуск обновляет те же строки по паре (сотрудник, абсолютный source_path).

Опции:
  --dry-run          выполнить импорт в транзакции и откатить (статистика печатается)
  --only-folder NAME обработать только один подкаталог корня (имя папки, например «1&Гезик» или «R&Регламенты»)
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from pass_docs.catalog.document_codes import catalog_defaults_for_import
from pass_docs.models import DocumentType, Employee, EmployeeDocument

COMMON_EMPLOYEE_CODE = "__COMMON_ORG__"


def _normalize_doc_code(raw: str) -> str:
    s = (raw or "").strip().upper().replace(" ", "_")
    cleaned = "".join(c for c in s if c.isalnum() or c in "_-")
    return cleaned[:64] if cleaned else "UNKNOWN"


def _split_fio(name_part: str) -> tuple[str, str, str, str]:
    """Возвращает (full_name, last_name, first_name, middle_name)."""
    name_part = (name_part or "").strip()
    if not name_part:
        return "", "", "", ""
    parts = name_part.split()
    if len(parts) >= 3:
        ln, fn = parts[0], parts[1]
        mn = " ".join(parts[2:])
        return name_part, ln, fn, mn
    if len(parts) == 2:
        return name_part, parts[0], parts[1], ""
    return name_part, name_part, "", ""


def _split_folder(folder_name: str) -> tuple[str, str]:
    """Префикс и остаток после первого «&» (информативно)."""
    if "&" not in folder_name:
        return folder_name.strip(), ""
    a, b = folder_name.split("&", 1)
    return a.strip(), b.strip()


def _empty_stats() -> dict[str, int]:
    return {
        "employees_created": 0,
        "employees_updated": 0,
        "document_types_created": 0,
        "document_types_updated": 0,
        "employee_documents_created": 0,
        "employee_documents_updated": 0,
        "files_seen": 0,
        "skipped_dirs": 0,
        "skipped_files": 0,
    }


class Command(BaseCommand):
    help = "Импорт pass_docs из папочной структуры (--root)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--root",
            type=str,
            required=True,
            help='Корень дерева, например "/path/to/Документы/PDF"',
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Выполнить импорт в транзакции и откатить изменения (статистика всё равно выводится).",
        )
        parser.add_argument(
            "--only-folder",
            type=str,
            default="",
            help='Имя одного подкаталога под --root, например "1&Гезик" или "R&Регламенты"',
        )

    def handle(self, *args, **options):
        root = Path(options["root"]).expanduser()
        if not root.is_dir():
            raise CommandError(f"Каталог не найден или не является папкой: {root}")

        self._root = root.resolve()
        dry_run = bool(options["dry_run"])
        only_folder = (options.get("only_folder") or "").strip()

        self.stdout.write(self.style.NOTICE(f"Корень импорта: {self._root}"))
        if dry_run:
            self.stdout.write(self.style.WARNING("Режим --dry-run: после завершения транзакция будет откатана."))
        if only_folder:
            self.stdout.write(self.style.NOTICE(f"Только папка: {only_folder!r}"))

        stats = _empty_stats()

        with transaction.atomic():
            common_employee = self._ensure_common_employee(stats)

            for entry in self._iter_target_entries(only_folder):
                if not entry.is_dir():
                    continue
                if "&" not in entry.name:
                    self.stderr.write(self.style.WARNING(f"Пропуск каталога без «&»: {entry.name}"))
                    stats["skipped_dirs"] += 1
                    continue

                prefix, rest = _split_folder(entry.name)
                pfx_up = prefix.upper()

                if pfx_up in ("R", "D"):
                    self._import_files_under(
                        entry,
                        common_employee,
                        from_common=True,
                        common_kind=pfx_up,
                        folder_label=rest,
                        stats=stats,
                    )
                else:
                    employee = self._ensure_personal_employee(entry.name, stats)
                    self._import_files_under(
                        entry,
                        employee,
                        from_common=False,
                        common_kind="",
                        folder_label="",
                        stats=stats,
                    )

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS("Импорт завершён."))
        for key in (
            "employees_created",
            "employees_updated",
            "document_types_created",
            "document_types_updated",
            "employee_documents_created",
            "employee_documents_updated",
            "files_seen",
            "skipped_dirs",
            "skipped_files",
        ):
            self.stdout.write(f"  {key}: {stats[key]}")

    def _iter_target_entries(self, only_folder: str):
        """Подкаталоги корня для обработки (все или один по --only-folder)."""
        if not only_folder:
            yield from sorted(self._root.iterdir(), key=lambda p: p.name.lower())
            return

        direct = self._root / only_folder
        if direct.is_dir() and direct.parent.resolve() == self._root:
            yield direct
            return

        for child in self._root.iterdir():
            if child.is_dir() and child.name == only_folder:
                yield child
                return

        raise CommandError(
            f"Папка {only_folder!r} не найдена непосредственно под корнем {self._root}"
        )

    def _ensure_common_employee(self, stats: dict) -> Employee:
        emp, created = Employee.objects.get_or_create(
            import_key=COMMON_EMPLOYEE_CODE,
            defaults={
                "source_folder_name": "",
                "source_prefix": "",
                "source_label": "",
                "employee_code": COMMON_EMPLOYEE_CODE,
                "full_name": "Общие документы (R/D)",
                "last_name": "",
                "first_name": "",
                "middle_name": "",
                "is_active": True,
                "notes": "Служебная запись для файлов из каталогов R& и D&.",
            },
        )
        if created:
            stats["employees_created"] += 1
        return emp

    def _ensure_personal_employee(self, folder_name: str, stats: dict) -> Employee:
        """
        Личный сотрудник: уникальность по полному имени папки (например 1&Гусев и 1&Гезик — разные записи).
        """
        folder_name = (folder_name or "").strip()
        if not folder_name or "&" not in folder_name:
            raise CommandError(f"Некорректное имя папки сотрудника: {folder_name!r}")

        prefix, label = _split_folder(folder_name)
        full_name, ln, fn, mn = _split_fio(label)
        if not full_name:
            full_name = folder_name

        emp, created = Employee.objects.update_or_create(
            import_key=folder_name,
            defaults={
                "source_folder_name": folder_name,
                "source_prefix": prefix,
                "source_label": label,
                "employee_code": None,
                "full_name": full_name,
                "last_name": ln,
                "first_name": fn,
                "middle_name": mn,
            },
        )
        if created:
            stats["employees_created"] += 1
        else:
            stats["employees_updated"] += 1
        return emp

    def _get_or_create_document_type(
        self, raw_code: str, *, from_common: bool, stats: dict
    ) -> DocumentType:
        code = _normalize_doc_code(raw_code)
        cat = catalog_defaults_for_import(code)
        defaults = {
            "name": (cat.get("name") if cat else None)
            or ((raw_code or code).strip() or code),
            "description": "",
            "sort_order": 0,
            "extractor_kind": (cat.get("extractor_kind") if cat else None) or "",
            "is_common_document": from_common,
            "expiry_rule_days": None,
        }
        dt, created = DocumentType.objects.get_or_create(
            code=code,
            defaults=defaults,
        )
        if created:
            stats["document_types_created"] += 1
        else:
            updates: list[str] = []
            if cat:
                if not (dt.extractor_kind or "").strip() and cat.get("extractor_kind"):
                    dt.extractor_kind = cat["extractor_kind"]
                    updates.append("extractor_kind")
                trivial_names = {code, (raw_code or "").strip(), ""}
                if dt.name.strip() in trivial_names and cat.get("name"):
                    dt.name = cat["name"][:255]
                    updates.append("name")
            if from_common and not dt.is_common_document:
                dt.is_common_document = True
                updates.append("is_common_document")
            if updates:
                dt.save(update_fields=updates)
                stats["document_types_updated"] += 1
        return dt

    def _relpath(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self._root))
        except ValueError:
            return str(path.resolve())

    def _import_files_under(
        self,
        folder: Path,
        employee: Employee,
        *,
        from_common: bool,
        common_kind: str,
        folder_label: str,
        stats: dict,
    ) -> None:
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            stats["files_seen"] += 1
            name = path.name
            if "&" not in name:
                stats["skipped_files"] += 1
                continue

            raw_code = name.split("&", 1)[0].strip()
            doc_type = self._get_or_create_document_type(
                raw_code, from_common=from_common, stats=stats
            )

            source_path = str(path.resolve())
            meta: dict = {
                "import_scope": "common" if from_common else "employee",
                "path_under_root": self._relpath(path),
            }
            if from_common:
                meta["common_folder_kind"] = common_kind
                meta["common_folder_label"] = folder_label
            else:
                meta["employee_folder"] = folder.name

            _ed, ed_created = EmployeeDocument.objects.update_or_create(
                employee=employee,
                source_path=source_path,
                defaults={
                    "document_type": doc_type,
                    "parse_status": EmployeeDocument.ParseStatus.PENDING,
                    "status": EmployeeDocument.Status.PENDING,
                    "is_actual": True,
                    "metadata": meta,
                    "extracted_json": {},
                    "external_reference": "",
                    "notes": "",
                },
            )
            if ed_created:
                stats["employee_documents_created"] += 1
            else:
                stats["employee_documents_updated"] += 1
