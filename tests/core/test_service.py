import sys
import unittest

from semaforos.service import commands


class ServiceCommandTests(unittest.TestCase):
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
