import unittest

from leads_workstation.normalize import fingerprint, normalize_email, normalize_phone


class NormalizeTests(unittest.TestCase):
    def test_email(self):
        self.assertEqual(normalize_email(" A@Example.COM "), "a@example.com")
    def test_phone(self):
        self.assertEqual(normalize_phone("+1 (617) 555-0199"), "6175550199")
    def test_fingerprint_prefers_email_without_canonical_id(self):
        self.assertEqual(
            fingerprint({"email_primary": "x@example.com", "phone": "1111111111"}),
            fingerprint({"email_primary": "X@example.com", "phone": "2222222222"}),
        )

    def test_canonical_lead_id_prevents_over_dedupe(self):
        self.assertNotEqual(
            fingerprint({"lead_id": "a", "email_primary": "shared@example.com"}),
            fingerprint({"lead_id": "b", "email_primary": "shared@example.com"}),
        )
if __name__ == "__main__":
    unittest.main()
