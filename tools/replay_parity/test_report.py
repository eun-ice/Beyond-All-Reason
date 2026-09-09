import json
import tempfile
import unittest
from pathlib import Path
from report import report


class ReportTests(unittest.TestCase):
    def test_completion_and_event_differences(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a', Path(tmp) / 'b'
            info = dict(engine_sha256='engine', complete=True, exit_code=0, lua_errors=False)
            for root in (a, b):
                root.mkdir()
                (root / 'run.json').write_text(json.dumps(info))
                (root / 'hashes.tsv').write_text('0\tstate\tevents\n150\tstate2\tevents2\n')
            self.assertEqual(report(a, b)['result'], 'equal')
            (b / 'run.json').write_text(json.dumps(dict(info, complete=False)))
            self.assertEqual(report(a, b)['result'], 'incomplete_or_incompatible')
            (b / 'run.json').write_text(json.dumps(info))
            (b / 'hashes.tsv').write_text('0\tstate\tevents\n150\tstate2\tdifferent\n')
            result = report(a, b)
            self.assertEqual(result['result'], 'different')
            self.assertIsNone(result['first_state_difference'])
            self.assertEqual(result['first_event_difference'], 150)


if __name__ == '__main__':
    unittest.main()
