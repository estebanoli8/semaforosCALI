import unittest
from semaforos.messages import is_team_sender

class SenderFilterTests(unittest.TestCase):
    def test_exact_normalized_team(self):
        self.assertTrue(is_team_sender('\u200eEsteban Oli'))
        self.assertTrue(is_team_sender(' Esteban   Oli '))
    def test_citizens_and_unknown_preserved(self):
        for sender in (None,'Esteban Oliveros','Esteban Oli vecino','María','+573001234567'):
            self.assertFalse(is_team_sender(sender))
