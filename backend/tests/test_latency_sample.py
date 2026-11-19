"""T18: local non-AI latency sampling (methodology evidence, not a production claim)."""
import unittest

from scripts.latency_sample import ENDPOINTS, measure


class LatencySampleTests(unittest.TestCase):
    def test_measure_reports_percentiles_and_gate(self):
        report = measure(samples=8)
        self.assertEqual(set(report['endpoints']), set(ENDPOINTS))
        for name, stats in report['endpoints'].items():
            self.assertEqual(stats['n'], 8, name)
            self.assertGreaterEqual(stats['p95_ms'], stats['p50_ms'])
            self.assertGreaterEqual(stats['max_ms'], stats['p95_ms'])
        self.assertEqual(report['overall']['n'], 8 * len(ENDPOINTS))
        self.assertEqual(report['gate_ms'], 500)
        self.assertLess(report['overall']['p95_ms'], 500)
        self.assertTrue(report['passed'])


if __name__ == '__main__':
    unittest.main()
