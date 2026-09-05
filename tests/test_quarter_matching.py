import unittest
from scripts.normalize_data import prior_economic_quarter


class QuarterMatchingTests(unittest.TestCase):
    def test_issuer_label_does_not_override_economic_period(self):
        rows = [
            {'period_end':'2024-01-31','fiscal_year':'2024','fiscal_quarter':'Q4'},
            {'period_end':'2025-01-31','fiscal_year':'2025','fiscal_quarter':'Q4'},
            {'period_end':'2026-01-31','fiscal_year':'2025','fiscal_quarter':'Q4'},
        ]
        self.assertEqual(prior_economic_quarter(rows, rows[-1])['period_end'], '2025-01-31')

    def test_53_week_fiscal_year_is_supported(self):
        rows = [{'period_end':'2025-01-26'}, {'period_end':'2026-02-01'}]
        self.assertEqual(prior_economic_quarter(rows, rows[-1])['period_end'], '2025-01-26')


if __name__ == '__main__':
    unittest.main()
