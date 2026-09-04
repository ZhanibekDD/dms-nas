from pathlib import Path
import unittest


_TEMPLATE_DIR = (
    Path(__file__).resolve().parents[2]
    / "adminpanel"
    / "templates"
    / "adminpanel"
)


class TestDocumentCodeVisibility(unittest.TestCase):
    def _template(self, filename: str) -> str:
        return (_TEMPLATE_DIR / filename).read_text(encoding="utf-8")

    def _assert_visible_code(self, filename: str, expression: str) -> None:
        content = self._template(filename)
        self.assertIn(
            f'<span class="pd-type-code">{expression}&amp;</span>',
            content,
        )
        self.assertNotIn('class="pd-type-code pd-user-hidden"', content)
        self.assertIn("Без кода — требуется разбор", content)

    def test_employee_page_shows_document_codes(self) -> None:
        self._assert_visible_code(
            "pass_docs_employee_detail.html",
            "{{ d.document_type.code }}",
        )

    def test_document_page_shows_document_code(self) -> None:
        self._assert_visible_code(
            "pass_docs_document_detail.html",
            "{{ doc.document_type.code }}",
        )

    def test_registry_shows_codes_and_uncoded_filter(self) -> None:
        self._assert_visible_code(
            "pass_docs_documents.html",
            "{{ doc.document_type.code }}",
        )
        content = self._template("pass_docs_documents.html")
        self.assertIn('name="code_status"', content)
        self.assertIn("{{ documents_uncoded }}", content)


if __name__ == "__main__":
    unittest.main()
