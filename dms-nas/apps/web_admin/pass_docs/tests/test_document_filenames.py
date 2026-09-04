from unittest import TestCase

from pass_docs.catalog.document_filenames import (
    MISSING_DOCUMENT_CODE,
    canonical_document_filename,
    infer_exact_document_code,
    is_supported_uncoded_document,
    normalize_document_code,
    parse_document_filename,
    safe_basename,
)


class DocumentFilenameTests(TestCase):
    def test_legacy_code_is_preserved(self):
        parsed = parse_document_filename("11&ВУ.pdf")
        self.assertEqual(parsed.code, "11")
        self.assertEqual(parsed.status, "coded")
        self.assertEqual(parsed.label, "ВУ.pdf")

    def test_confirmed_vu_alias_is_inferred_exactly(self):
        parsed = parse_document_filename("ВУ.pdf")
        self.assertEqual(parsed.code, "11")
        self.assertEqual(parsed.status, "inferred")
        self.assertEqual(infer_exact_document_code("водительское_удостоверение.PDF"), "11")

    def test_unknown_uncoded_file_is_explicitly_missing(self):
        parsed = parse_document_filename("новый документ.pdf")
        self.assertEqual(parsed.code, MISSING_DOCUMENT_CODE)
        self.assertEqual(parsed.status, "missing")

    def test_no_fuzzy_guess_for_similar_name(self):
        self.assertIsNone(infer_exact_document_code("ВУ новое.pdf"))

    def test_supported_extensions_are_case_insensitive(self):
        self.assertTrue(is_supported_uncoded_document("scan.PDF"))
        self.assertTrue(is_supported_uncoded_document("scan.docx"))
        self.assertFalse(is_supported_uncoded_document("Thumbs.db"))

    def test_windows_and_posix_paths_are_reduced_to_basename(self):
        self.assertEqual(safe_basename(r"C:\\staff\\ВУ.pdf"), "ВУ.pdf")
        self.assertEqual(safe_basename("../../11&ВУ.pdf"), "11&ВУ.pdf")

    def test_code_normalization_is_bounded(self):
        self.assertEqual(normalize_document_code(" passport rf "), "PASSPORT_RF")
        self.assertEqual(normalize_document_code(""), MISSING_DOCUMENT_CODE)
        self.assertEqual(len(normalize_document_code("x" * 100)), 64)

    def test_canonical_name_adds_authoritative_code(self):
        self.assertEqual(canonical_document_filename("11", "ВУ.pdf"), "11&ВУ.pdf")
        self.assertEqual(
            canonical_document_filename("11", "99&старое имя.pdf"),
            "11&старое имя.pdf",
        )
