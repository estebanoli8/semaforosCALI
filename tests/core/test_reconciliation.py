import unittest
from semaforos.reconciliation import compare

def m(body,stamp='01/11/26, 10:00',sender='Vecina'):
    return dict(kind='message',sender_visible=sender,timestamp_literal=stamp,body_text=body)

class ReconciliationTests(unittest.TestCase):
    def test_extension_preserves_duplicate_occurrences(self):
        r=compare([m('A'),m('A')],[m('A'),m('A'),m('B')])
        self.assertEqual(r['relation'],'derecha_contiene_izquierda')
        self.assertEqual(r['shared_occurrences'],2)
        self.assertEqual(r['right_only_occurrences'],1)
    def test_same_words_different_date_are_not_same_observation(self):
        self.assertEqual(compare([m('A')],[m('A',stamp='02/11/26, 10:00')])['shared_occurrences'],0)
    def test_reordered_history_is_not_extension(self):
        self.assertEqual(compare([m('A'),m('B')],[m('B'),m('A'),m('C')])['relation'],'solapamiento_parcial')
    def test_unknown_dates_and_system_messages_are_excluded(self):
        r=compare([m('A',stamp=None)],[m('A',stamp=None)])
        self.assertEqual(r['relation'],'sin_coincidencia');self.assertEqual(r['left_uncomparable'],1)
    def test_identical_text_does_not_confirm_identity_or_files(self):
        r=compare([m('A')],[m('A')])
        self.assertEqual(r['relation'],'mensajes_comparables_identicos')
        self.assertFalse(r['same_conversation_confirmed']);self.assertFalse(r['attachments_compared'])
    def test_missing_occurrence_is_counted(self):
        r=compare([m('A'),m('A')],[m('A')])
        self.assertEqual(r['left_only_occurrences'],1)
    def test_sender_mismatch(self):
        self.assertEqual(compare([m('A')],[m('A',sender='Otro')])['shared_occurrences'],0)
