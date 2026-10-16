"""Reviewed evidence can detect missing conditions without coaching the model."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

from app.access.search_intent import IntentUnavailable
import qualify_search_intent as qualify
import search_intent_cases as original
import search_intent_review_cases as reviewed


# Test-only linguistic alternatives, independent of the evidence annotations.
# These are never imported by the executable qualifier or a native worker.
ALTERNATIVES = {
    'yellow_coat': ['yellow coat', '黄色外套'],
    'waving': ['waves', 'waving', '挥手'],
    'beside_mailbox': ['beside a red mailbox', 'beside the red mailbox', '在红色邮箱旁'],
    'red_backpack': ['red backpack', '红色背包'],
    'carrying_backpack': ['carries', '背着'],
    'entering_cabin': ['walking into a wooden cabin', 'walks into the wooden cabin', '走进木屋'],
    'orange_gloves': ['orange gloves', '橙色手套'],
    'putting_gloves': ['puts', '放进', '把橙色手套放在'],
    'inside_canvas_basket': ['into a canvas basket', 'inside the canvas basket',
                             '放进帆布篮里', '放在帆布篮里'],
}


def description(case, *, omit=None):
    return {'version': 1, 'concepts': [
        {'surface': key, 'alternatives': ALTERNATIVES[key]}
        for key in case['conditions'] if key != omit]}


class RefusingPlanner:
    model = 'fictional-test-model'

    def __init__(self):
        self.calls = []

    def propose(self, *args):
        self.calls.append(args)
        raise IntentUnavailable()


class ReviewedIntentEvaluationTests(unittest.TestCase):
    def test_separate_plan_audits_all_conditions_without_provider_or_original_fixture_changes(self):
        with mock.patch.object(qualify, 'LocalIntentPlanner', side_effect=AssertionError('provider')):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, qualify.main(['--suite', 'reviewed-v1']))
        report = json.loads(output.getvalue())
        self.assertEqual(('plan_only', 'reviewed-v1', 12, 0),
                         (report['status'], report['suite'], report['case_count'], report['provider_calls']))
        self.assertEqual({'en': 4, 'zh': 4, 'mixed': 4}, report['cohort_counts'])
        self.assertEqual({'annotation_structure_verified': True, 'semantic_truth_verified': False,
                          'annotations_sent_to_provider': False, 'conditions': 27,
                          'positive_assets': 18, 'negative_assets': 27}, report['fixture_audit'])
        self.assertEqual('ae1379b1bea7850a26dd30b4e076f0b6e43574f80def6a5e7b19d304a71972de',
                         report['cases_sha256'])
        self.assertEqual('9136234e0f3530f41064f4511dd4430cb3feed2600f302042bac75a3efcfce61',
                         original.cases_digest())
        self.assertNotIn('suite', qualify.plan_summary())
        self.assertFalse(report['quality_evaluated'])

    def test_incomplete_positive_support_stale_quotes_and_missing_negative_coverage_refuse(self):
        corruptions = []
        cases = deepcopy(reviewed.CASES)
        cases[0]['evidence'][0]['support_quotes'].pop('beside_mailbox')
        corruptions.append(cases)
        cases = deepcopy(reviewed.CASES)
        cases[0]['evidence'][0]['sources'][0]['content'] = 'Mira waves in her yellow coat.'
        corruptions.append(cases)
        cases = deepcopy(reviewed.CASES)
        cases[0]['evidence'][0]['support_quotes']['waving']['source_id'] = 'another-asset'
        corruptions.append(cases)
        cases = deepcopy(reviewed.CASES)
        cases[0]['evidence'].pop()  # Lose the only isolated spatial-relation negative.
        corruptions.append(cases)
        cases = deepcopy(reviewed.CASES)
        cases[0]['evidence'].append(deepcopy(cases[0]['evidence'][0]))
        cases[0]['evidence'][-1]['asset_id'] += '-extra'
        corruptions.append(cases)
        cases = deepcopy(reviewed.CASES)
        cases[0]['evidence'][2]['support_quotes'].pop('waving')
        cases[0]['evidence'][2]['missing_conditions'].append('waving')
        corruptions.append(cases)
        cases = deepcopy(reviewed.CASES)
        cases[3]['expected_question'] = 'person'
        corruptions.append(cases)
        corruptions.append(())
        for cases in corruptions:
            with self.subTest(cases=len(cases)):
                with self.assertRaisesRegex(ValueError, 'reviewed_fixture_invalid'):
                    qualify.audit_reviewed_cases(cases)

    def test_real_matcher_checks_cross_language_evidence_and_each_omitted_condition(self):
        positive_total, negative_total = 0, 0
        for case in reviewed.CASES:
            if case['expected_status'] != 'ready':
                continue
            with self.subTest(case=case['id']):
                checks, met = qualify._evaluate_evidence(case, description(case))
                self.assertTrue(met, checks)
                positive_total += sum(c['expected_match'] is True for c in checks)
                negative_total += sum(c['expected_match'] is False for c in checks)
                for condition in case['conditions']:
                    weakened, _ = qualify._evaluate_evidence(case, description(case, omit=condition))
                    actual = {c['fixture_id']: c['actual_match'] for c in weakened}
                    isolated = next(a for a in case['evidence']
                                    if a['missing_conditions'] == [condition])
                    self.assertTrue(actual[isolated['asset_id']], condition)
        self.assertEqual((18, 27), (positive_total, negative_total))

    def test_refused_plans_keep_every_missed_positive_and_do_not_send_review_annotations(self):
        planner = RefusingPlanner()
        report = qualify.run_qualification(planner, suite='reviewed-v1')
        self.assertEqual(12, report['attempted_case_count'])
        self.assertEqual(len(planner.calls), report['provider_attempt_count'])
        self.assertLessEqual(len(planner.calls), 9)
        self.assertEqual(12, report['provider_attempt_count'] + report['provider_not_needed_count'])
        evidence = report['diagnostics']['overall']['evidence']
        self.assertEqual((0, 18, 0, 27, 9),
                         (evidence['positive_hits'], evidence['positive_total'],
                          evidence['negative_false_positives'], evidence['negative_total'],
                          evidence['skipped_expected_ready_case_count']))
        self.assertFalse(evidence['positive_recall_met'])
        self.assertFalse(evidence['negative_false_positive_expectation_met'])
        self.assertEqual(3, sum(row['expectations_met'] for row in report['cases']))
        self.assertTrue(all(row['hard_filters_preserved'] for row in report['cases']
                            if row['expected_status'] == 'clarification'))

        changed = deepcopy(reviewed.CASES)
        for case in changed:
            for key in case['conditions']:
                case['conditions'][key] = 'review-annotation-must-never-reach-provider'
        other = RefusingPlanner()
        with mock.patch.object(reviewed, 'CASES', changed):
            qualify.run_qualification(other, suite='reviewed-v1')
        self.assertEqual(planner.calls, other.calls)
        for view, today, previous in planner.calls:
            self.assertNotIn('Mira', view)
            self.assertNotIn('米拉', view)
            self.assertNotIn('paper workshop', view)
            self.assertNotIn('2032', view)
            self.assertEqual(('2032-09-14', False), (today, previous))

    def test_reviewed_cli_writes_a_separate_private_complete_report(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve() / 'reviewed.private.json'
            planner = RefusingPlanner()
            with mock.patch.object(qualify, 'LocalIntentPlanner', return_value=planner):
                with redirect_stdout(io.StringIO()):
                    code = qualify.main(['--run', '--suite', 'reviewed-v1', '--url',
                                         'http://127.0.0.1:11439', '--model', planner.model,
                                         '--out', str(target)])
            self.assertEqual(0, code)  # Complete measurement, not a quality pass.
            report = json.loads(target.read_text())
            self.assertEqual('reviewed-v1', report['suite'])
            self.assertEqual(reviewed.cases_digest(), report['cases_sha256'])
            self.assertFalse(report['native_runtime_verified'])
            self.assertFalse(report['family_quality_evaluated'])
            self.assertFalse(report['activation_performed'])
            self.assertEqual(0, target.stat().st_mode & 0o077)


if __name__ == '__main__':
    unittest.main()
