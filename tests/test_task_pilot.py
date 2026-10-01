import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('pilot',Path(__file__).resolve().parents[1]/'scripts/setup-pilot.py')
pilot=importlib.util.module_from_spec(spec);spec.loader.exec_module(pilot)


class PilotTests(unittest.TestCase):
    def test_no_human_data_remains_unobserved(self):
        self.assertEqual(pilot.report([])['evidence'],'not_observed')
        self.assertEqual(pilot.report([{'actor':'simulation','status':'finished'}])['completed_human_attempts'],0)

    def test_quality_failure_beats_speed(self):
        rows=[]
        for i in range(8):
            for arm,seconds in [('baseline',200),('candidate',100)]:
                rows.append({'actor':'human','status':'finished','pair':str(i),'condition':arm,'attention_seconds':seconds,'corrections':0,'quality':'pass','useful':'yes','session':str(i//2),'started_at':'2026-09-30T12:00:00+00:00'})
        self.assertEqual(pilot.report(rows)['attention_quality_gate'],'pass')
        self.assertEqual(pilot.report(rows)['promotion'],'not_decided')
        for bad in (float('nan'), float('inf'), -1):
            with self.assertRaises(ValueError):
                pilot.report([dict(rows[0], attention_seconds=bad)])
        orphan=dict(rows[0], pair='orphan', quality='fail')
        self.assertNotEqual(pilot.report(rows+[orphan])['attention_quality_gate'],'pass')
        one_session=[dict(r,session='same') for r in rows]
        self.assertNotEqual(pilot.report(one_session)['attention_quality_gate'],'pass')
        stale=[dict(r) for r in rows]; stale[0]['started_at']='2026-08-01T12:00:00+00:00'
        self.assertNotEqual(pilot.report(stale)['attention_quality_gate'],'pass')
        rows[-1]['quality']='critical_failure'
        self.assertEqual(pilot.report(rows)['attention_quality_gate'],'fail')
        rows[-1]['status']='abandoned'
        self.assertEqual(pilot.report(rows)['attention_quality_gate'],'fail')


if __name__=='__main__':unittest.main()
