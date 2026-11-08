import unittest
from tools.compare_runs import compare

class CompareTests(unittest.TestCase):
    def run_data(self, value, direction='lower'):
        return dict(dataset_id='d', labels_version='l', metrics={'wer':dict(value=value,direction=direction)})
    def test_lower_is_better_and_regression_visible(self):
        self.assertIn('Mejora', compare(self.run_data(.3), self.run_data(.2)))
        self.assertIn('Empeora', compare(self.run_data(.2), self.run_data(.3)))
    def test_dataset_mismatch(self):
        b=self.run_data(.2);b['dataset_id']='other'
        with self.assertRaises(ValueError):compare(self.run_data(.3), b)
    def test_missing_is_not_zero(self):
        self.assertIn('Sin comparación', compare(self.run_data(None),self.run_data(.2)))
    def test_invalid_metric_rejected(self):
        with self.assertRaises(ValueError):compare(self.run_data(float('nan')),self.run_data(.2))
    def test_direction_mismatch(self):
        with self.assertRaises(ValueError):compare(self.run_data(.2),self.run_data(.3,'higher'))
