"""Unit tests for metrics derived from the latest human review per run."""
import unittest

from semaforos.quality_metrics import summarize_reviews


class QualityMetricsTest(unittest.TestCase):
    def test_yolo_count_error_metrics(self):
        result=summarize_reviews([
            {'stage':'detect','human_label':{'observed':2,'detected':2}},
            {'stage':'detect','human_label':{'observed':3,'detected':2}},
            {'stage':'detect','human_label':{'observed':0,'detected':1}},
        ])['detect']
        self.assertEqual(result['samples'],3)
        self.assertAlmostEqual(result['exact_rate'],1/3)
        self.assertEqual(result['within_one_rate'],1)
        self.assertAlmostEqual(result['mae'],2/3)
        self.assertAlmostEqual(result['rmse'],(2/3)**.5)
        self.assertEqual(result['mean_bias'],0)
        self.assertAlmostEqual(result['relative_abs_error'],2/5)
        self.assertEqual((result['over'],result['under']),(1,1))

    def test_semantic_confusion_and_aggregate_metrics(self):
        result=summarize_reviews([
            {'stage':'text','human_label':{
                'dano':{'observed':True,'detected':True},
                'gestion':{'observed':False,'detected':False},
                'ubicacion':{'observed':True,'detected':False},
            }},
            {'stage':'text','human_label':{
                'dano':{'observed':False,'detected':True},
                'gestion':{'observed':True,'detected':True},
                'ubicacion':{'observed':False,'detected':False},
            }},
        ])['text']
        self.assertEqual(result['evaluations'],2)
        self.assertEqual(result['fields_evaluated'],6)
        self.assertEqual(result['exact_evaluations'],0)
        self.assertAlmostEqual(result['label_accuracy'],4/6)
        self.assertEqual(result['fields']['dano']['tp'],1)
        self.assertEqual(result['fields']['dano']['fp'],1)
        self.assertAlmostEqual(result['fields']['dano']['precision'],.5)
        self.assertEqual(result['fields']['gestion']['f1'],1)
        self.assertAlmostEqual(result['micro']['f1'],4/6)


if __name__=='__main__':
    unittest.main()
