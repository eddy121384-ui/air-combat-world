"""Measurement integrity regressions; no UE runtime dependency."""
import os
import json
import tempfile
import time
import unittest
from pathlib import Path

from perf_integrity import read_csv, sha256, validate_run
from analyze_perf import classification


class PerfIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv = Path(self.tmp.name) / "Profile.csv"
        self.log = Path(self.tmp.name) / "engine.log"
        self.started = time.time() - 1
        self.header = "EVENTS,FrameTime,GameThreadTime,RenderThreadTime,RHIThreadTime,GPUTime"
        self.metadata = '[tag],r1,[level],L_FSP_A_static,[run_id],abc,[csvid],capture1,[targetframerate],60,[vsyncenabled],0,[systemresolution.resx],1920,[systemresolution.resy],1080,[gpu],Intel(R) UHD Graphics 770'
        self.rows = [",20,2,3,1,18"] * 4
        self.write_csv()
        self.log_text = '\n'.join(['Metadata set : tag="r1"', 'Metadata set : level="L_FSP_A_static"',
            'Metadata set : run_id="abc"', 'Capture started. CSV ID: capture1',
            'Bringing World /Game/ForestSpike/Perf/L_FSP_A_static.L_FSP_A_static up for play',
            'Capture Ended. Writing CSV to file : ../Profile.csv', 'LogCsvProfiler: Display:   Frames : 4',
            'CSV finalize time : 0.01 seconds', 'RequestExit(0, CsvProfiler.ExitAfterCsvProfiling)'])
        self.log.write_text(self.log_text)

    def write_csv(self):
        self.csv.write_text('\n'.join([self.header] + self.rows + [self.header, self.metadata]))

    def validate(self, **kwargs):
        args = dict(tag="r1", level="L_FSP_A_static", run_id="abc", frames=4, cold=1,
                    started_epoch=self.started, exit_code=0)
        args.update(kwargs)
        return validate_run(self.csv, self.log, **args)

    def assertFail(self, **kwargs):
        result = self.validate(**kwargs)
        self.assertEqual(result["status"], "FAIL_FS_PERF")
        self.assertTrue(result["errors"])

    def test_valid_capture(self):
        self.assertEqual(self.validate()["status"], "PASS_FS_PERF_CAPTURE")

    def test_explicit_isolated_world_path(self):
        new_path = '/Game/ForestSpike/B01_test/Perf/L_FSP_A_static'
        self.log.write_text(self.log_text.replace('/Game/ForestSpike/Perf/L_FSP_A_static', new_path))
        self.assertEqual(self.validate(world_path=new_path)['status'], 'PASS_FS_PERF_CAPTURE')

    def test_explicit_world_does_not_accept_original_map(self):
        self.assertFail(world_path='/Game/ForestSpike/B01_test/Perf/L_FSP_A_static')

    def test_shutdown_crash_after_completion_is_disclosed(self):
        result = self.validate(exit_code=-1073741819)
        self.assertEqual(result["status"], "PASS_FS_PERF_CAPTURE")
        self.assertTrue(result["shutdown_crash_after_completion"])

    def test_csv_without_completion_fails_even_exit_zero(self):
        self.log.write_text('started only')
        self.assertFail()

    def test_early_crash_fails(self):
        self.log.write_text('Unhandled Exception: access violation\n' + self.log_text)
        self.assertFail(exit_code=-1073741819)

    def test_wrong_level(self):
        self.assertFail(level='L_FSP_B_static')

    def test_wrong_tag(self):
        self.assertFail(tag='old')

    def test_wrong_run_id(self):
        self.assertFail(run_id='old')

    def test_wrong_frames(self):
        self.assertFail(frames=5)

    def test_unobserved_exit(self):
        self.assertFail(exit_code=None)

    def test_stale_csv(self):
        os.utime(self.csv, (self.started - 10, self.started - 10))
        self.assertFail()

    def test_stale_log(self):
        os.utime(self.log, (self.started - 10, self.started - 10))
        self.assertFail()

    def test_missing_gpu_column(self):
        self.header = self.header.replace('GPUTime', 'Other')
        self.write_csv()
        self.assertFail()

    def test_nan_numeric(self):
        self.rows[2] = ',20,2,3,1,nan'
        self.write_csv()
        self.assertFail()

    def test_zero_warm_gpu(self):
        self.rows[2] = ',20,2,3,1,0'
        self.write_csv()
        self.assertFail()

    def test_truncated_required_column(self):
        self.rows[2] = ',20,2,3,1'
        self.write_csv()
        self.assertFail()

    def test_legacy_decoded_but_cannot_pass_new_capture(self):
        self.metadata = self.metadata.replace('[tag],r1,[level],L_FSP_A_static', '[tag],r1;level=L_FSP_A_static')
        self.write_csv()
        data = read_csv(self.csv)
        self.assertEqual(data['metadata']['level'], 'L_FSP_A_static')
        self.assertTrue(data['legacy_metadata'])
        self.assertFail()

    def test_duplicate_metadata_fails(self):
        self.metadata += ',[tag],r1'
        self.write_csv()
        self.assertFail()

    def test_wrong_world_in_log(self):
        self.log.write_text(self.log_text.replace('Bringing World /Game/ForestSpike', 'Bringing World /Game/Wrong'))
        self.assertFail()

    def test_wrong_capture_id_in_log(self):
        self.log.write_text(self.log_text.replace('CSV ID: capture1', 'CSV ID: another'))
        self.assertFail()

    def test_wrong_resolution(self):
        self.metadata = self.metadata.replace('[systemresolution.resx],1920', '[systemresolution.resx],1280')
        self.write_csv()
        self.assertFail()

    def test_optional_late_column_retains_alignment(self):
        self.header += ',OptionalLateStat'
        self.write_csv()
        data = read_csv(self.csv)
        self.assertEqual(data['columns']['GPUTime'], [18] * 4)
        self.assertEqual(data['omitted_optional'], {'OptionalLateStat': 4})

    def test_unescaped_ue_commandline_tail_is_preserved(self):
        commandline = ' project -ExecCmds="r.VSync 0,t.MaxFPS 0" -csvMetadata=tag=r1,level=L_FSP_A_static'
        self.metadata += ',[commandline],"' + commandline + '"'
        self.write_csv()
        self.assertEqual(read_csv(self.csv)['metadata']['commandline'], commandline)

    def test_analyzer_does_not_promote_csv_without_receipt(self):
        self.assertEqual(classification(self.csv, read_csv(self.csv)['metadata']), 'HISTORICAL_ONLY_UNVERIFIED')

    def test_analyzer_rejects_changed_csv_after_receipt(self):
        receipt = self.validate()
        (self.csv.parent / 'completion.json').write_text(json.dumps(receipt))
        self.rows[2] = ',21,2,3,1,19'
        self.write_csv()
        self.assertEqual(classification(self.csv, read_csv(self.csv)['metadata']), 'FAIL_FS_PERF_CAPTURE')

    def test_analyzer_accepts_verified_receipt(self):
        receipt = self.validate()
        (self.csv.parent / 'completion.json').write_text(json.dumps(receipt))
        self.assertEqual(classification(self.csv, read_csv(self.csv)['metadata']), 'PASS_FS_PERF_CAPTURE')


if __name__ == '__main__':
    unittest.main()
