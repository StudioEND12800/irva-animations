import unittest

from app.utils import infer_department_code, infer_region


class RegionInferenceTests(unittest.TestCase):
    def test_department_from_clean_postal_code(self):
        self.assertEqual(infer_department_code("12850"), "12")
        self.assertEqual(infer_department_code("06340"), "06")

    def test_department_from_loose_text(self):
        self.assertEqual(infer_department_code("59 mille quelque chose"), "59")
        self.assertEqual(infer_department_code("13783"), "13")

    def test_department_from_overseas_postal_code(self):
        self.assertEqual(infer_department_code("97122"), "971")
        self.assertEqual(infer_region("97122"), "Guadeloupe")

    def test_region_from_postal_code(self):
        self.assertEqual(infer_region("12850"), "Occitanie")
        self.assertEqual(infer_region("62100"), "Hauts-de-France")
        self.assertEqual(infer_region("77240"), "Ile-de-France")


if __name__ == "__main__":
    unittest.main()
