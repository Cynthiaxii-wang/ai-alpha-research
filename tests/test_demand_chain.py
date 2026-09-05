"""Demand-chain availability and missing-data regression checks."""
import unittest
from datetime import date, timedelta
from ai_alpha_research.demand_chain import build_demand_chain


class DemandChainTests(unittest.TestCase):
    def build(self, usage=(), quarterly=()):
        return build_demand_chain([], usage, [], quarterly, '2026-09-05T00:00:00Z')

    def test_complete_weeks_and_unavailable_revision(self):
        rows = [{'usage_date': (date(2026, 9, 4)-timedelta(days=i)).isoformat(),
                 'model_permaslug': 'other', 'total_tokens': 20 if i < 7 else 10,
                 'available_at': '2026-09-04T23:00:00Z'} for i in range(14)]
        rows.append(dict(rows[0], total_tokens=99999, available_at='2026-09-06T00:00:00Z'))
        result = self.build(rows)['consumption']
        self.assertEqual(result['value'], 140)
        self.assertEqual(result['change'], 1)
        self.assertEqual(result['otherShare'], 1)
        self.assertIsNone(self.build(rows[1:-1])['consumption']['change'])

    def test_missing_fiscal_year_is_not_fabricated(self):
        rows = [{'ticker':'MSFT','period_end':'2026-06-30',
                 'available_date':'2026-07-30','revenue':100,'free_cash_flow':20}]
        result = self.build(quarterly=rows)['companies'][0]
        self.assertEqual(result['fcfMargin'], .2)
        self.assertIsNone(result['fcfMarginYoYDelta'])
        self.assertEqual(result['flag'], '继续跟踪投入兑现')

    def test_same_economic_quarter_despite_bad_sec_label(self):
        rows = [dict(ticker='MSFT',period_end=d,available_date=d,fiscal_year=y,
                     fiscal_quarter=q,fcf_margin=m,revenue=100,free_cash_flow=m*100)
                for d,y,q,m in [('2025-06-30',2025,'Q4',.2),
                                ('2026-03-31',2026,'Q3',.9),
                                ('2026-06-30',2025,'Q4',.3)]]
        self.assertAlmostEqual(self.build(quarterly=rows)['companies'][0]['fcfMarginYoYDelta'], .1)


if __name__ == '__main__':
    unittest.main()
