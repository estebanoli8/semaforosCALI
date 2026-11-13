import sys
import unittest
from unittest.mock import patch

from semaforos.service import commands


class ServiceCommandTests(unittest.TestCase):
    def test_parallel_mode_starts_two_bounded_lanes(self):
        with patch.dict('os.environ',{'SC_PARALLEL':'1'}):
            specs=commands('all')
            self.assertEqual(len(specs),3)
            self.assertEqual([s[-1] for s in specs[1:]],['text','media'])
            self.assertEqual(len(commands('api')),1)

    def test_all_starts_api_and_worker(self):
        specs = commands("all")
        self.assertEqual(2, len(specs))
        self.assertEqual([sys.executable, "-m", "uvicorn"], specs[0][:3])
        self.assertEqual([sys.executable, "-m", "semaforos", "worker"], specs[1])

    def test_invalid_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "SC_PROCESS"):
            commands("unknown")


if __name__ == "__main__":
    unittest.main()
