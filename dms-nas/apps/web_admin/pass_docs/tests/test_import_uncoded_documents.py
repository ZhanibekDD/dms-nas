from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from pass_docs.models import Employee, EmployeeDocument


class ImportUncodedDocumentsTests(TestCase):
    def test_uncoded_documents_are_visible_and_idempotent(self):
        with TemporaryDirectory() as tmp:
            employee_dir = Path(tmp) / "1&Тестовый"
            employee_dir.mkdir()
            (employee_dir / "ВУ.pdf").write_bytes(b"%PDF-1.4")
            (employee_dir / "новый документ.pdf").write_bytes(b"%PDF-1.4")
            (employee_dir / "Thumbs.db").write_bytes(b"not-a-document")

            call_command("import_pass_docs", root=tmp)
            call_command("import_pass_docs", root=tmp)

            employee = Employee.objects.get(import_key="1&Тестовый")
            docs = {
                Path(doc.source_path).name: doc
                for doc in EmployeeDocument.objects.filter(employee=employee)
            }
            self.assertEqual(set(docs), {"ВУ.pdf", "новый документ.pdf"})

            inferred = docs["ВУ.pdf"]
            self.assertEqual(inferred.document_type.code, "11")
            self.assertEqual(
                inferred.metadata["document_code_status"],
                "inferred",
            )
            self.assertEqual(
                inferred.metadata["canonical_filename"],
                "11&ВУ.pdf",
            )

            missing = docs["новый документ.pdf"]
            self.assertEqual(missing.document_type.code, "UNKNOWN")
            self.assertEqual(
                missing.metadata["document_code_status"],
                "missing",
            )
            self.assertEqual(
                missing.parse_status,
                EmployeeDocument.ParseStatus.SKIPPED,
            )

    def test_existing_coded_filename_remains_coded(self):
        with TemporaryDirectory() as tmp:
            employee_dir = Path(tmp) / "1&Тестовый"
            employee_dir.mkdir()
            (employee_dir / "6&Паспорт.pdf").write_bytes(b"%PDF-1.4")

            call_command("import_pass_docs", root=tmp)

            doc = EmployeeDocument.objects.get(employee__import_key="1&Тестовый")
            self.assertEqual(doc.document_type.code, "6")
            self.assertEqual(doc.metadata["document_code_status"], "coded")
            self.assertEqual(
                doc.metadata["canonical_filename"],
                "6&Паспорт.pdf",
            )
