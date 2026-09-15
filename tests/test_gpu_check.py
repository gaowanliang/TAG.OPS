import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

from app.gpu_check import active_adapters, engine_snapshot, observe_inference, session_check

DML = "DmlExecutionProvider"
CPU = "CPUExecutionProvider"
GPU = {"id": 2, "name": "NVIDIA", "luid": "00000000:0000000a"}
OTHER = {"id": 0, "name": "Intel", "luid": "00000000:0000000b"}


def counter(luid="A", engine="3D"):
    return f"pid_123_luid_0x00000000_0x0000000{luid}_phys_0_eng_0_engtype_{engine}"


class GPUCheckTests(unittest.TestCase):
    def setUp(self):
        sleep = patch("app.gpu_check.time.sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def check(self):
        session = Mock()
        session.get_providers.return_value = [DML, CPU]
        session.get_provider_options.return_value = {DML: {}}
        return session_check(session, DML, GPU)

    def test_configuration_alone_never_verifies_activity(self):
        check = self.check()
        self.assertEqual(check["status"], "pending")
        self.assertIsNone(check["reported_device_id"])
        self.assertEqual(check["registered_providers"], [DML, CPU])

    def test_cpu_fallback_and_wrong_runtime_device(self):
        session = Mock()
        session.get_providers.return_value = [CPU]
        self.assertEqual(session_check(session, DML, GPU)["status"], "fallback")
        session.get_providers.return_value = [DML, CPU]
        session.get_provider_options.return_value = {DML: {"device_id": "0"}}
        self.assertEqual(session_check(session, DML, GPU)["status"], "mismatch")

    def test_telemetry_outcomes(self):
        for after, expected in [
            ({counter(): 110}, "verified"),
            ({counter("B"): 110}, "mismatch"),
            ({counter(): 100}, "unverified"),
            ({counter(engine="Copy"): 110}, "unverified"),
            ({counter(): 110, counter("B"): 110}, "unverified"),
        ]:
            with self.subTest(after=after):
                check = self.check()
                infer = Mock(return_value="tags")
                with patch("app.dxgi.enumerate_adapters", return_value=[GPU, OTHER]), \
                        patch("app.gpu_check.engine_snapshot", side_effect=[{counter(): 100}, after, after]):
                    self.assertEqual(observe_inference(check, infer), "tags")
                self.assertEqual(check["status"], expected)
                infer.assert_called_once()

    def test_delayed_counter_publication_can_verify_without_repeating_inference(self):
        check, infer = self.check(), Mock(return_value="tags")
        with patch("app.dxgi.enumerate_adapters", return_value=[GPU]), \
                patch("app.gpu_check.engine_snapshot", side_effect=[{}, {}, {counter(): 110}]) as snapshot, \
                patch("app.gpu_check.time.monotonic", return_value=10):
            self.assertEqual(observe_inference(check, infer), "tags")
        self.assertEqual(check["status"], "verified")
        self.assertEqual(snapshot.call_count, 3)
        self.assertEqual(len(check["telemetry"]["samples"]), 2)
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [1, 1])
        infer.assert_called_once()

    def test_empty_idle_copy_and_unknown_counters_have_distinct_diagnostics(self):
        for after, reason in [
            ({}, "no_process_counters"),
            ({counter(): 0}, "no_compute_delta"),
            ({counter(engine="Copy"): 110}, "non_compute_activity"),
            ({"unsupported_name": 10}, "unrecognized_engines"),
        ]:
            with self.subTest(reason=reason):
                check, infer = self.check(), Mock()
                with patch("app.dxgi.enumerate_adapters", return_value=[GPU]), \
                        patch("app.gpu_check.engine_snapshot", return_value=after) as snapshot:
                    # Only the before/after delta matters; model was idle before the probe.
                    snapshot.side_effect = [{}, after, after]
                    observe_inference(check, infer)
                self.assertEqual(check["status"], "unverified")
                self.assertEqual(check["reason"], reason)
                self.assertEqual(snapshot.call_count, 3)
                infer.assert_called_once()

    def test_post_inference_counter_failure_never_reruns_image(self):
        check, infer = self.check(), Mock(return_value="tags")
        with patch("app.dxgi.enumerate_adapters", return_value=[GPU]), \
                patch("app.gpu_check.engine_snapshot", side_effect=[{}, OSError("counter failed")]):
            self.assertEqual(observe_inference(check, infer), "tags")
        self.assertEqual(check["reason"], "counter_collection_failed")
        self.assertIn("counter failed", check["telemetry"]["error"])
        infer.assert_called_once()

    def test_missing_counters_are_inconclusive_and_inference_still_runs(self):
        check = self.check()
        infer = Mock(return_value="tags")
        with patch("app.dxgi.enumerate_adapters", return_value=[GPU]), \
                patch("app.gpu_check.engine_snapshot", side_effect=OSError("disabled")):
            self.assertEqual(observe_inference(check, infer), "tags")
        self.assertEqual(check["status"], "unverified")
        infer.assert_called_once()

    def test_inference_errors_are_not_swallowed_or_retried(self):
        infer = Mock(side_effect=RuntimeError("inference failed"))
        with patch("app.dxgi.enumerate_adapters", return_value=[GPU]), \
                patch("app.gpu_check.engine_snapshot", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "inference failed"):
                observe_inference(self.check(), infer)
        infer.assert_called_once()

    def test_same_named_devices_do_not_prove_identity(self):
        check = self.check()
        check["expected_device"] = {"id": 2, "name": "NVIDIA"}
        with patch("app.dxgi.enumerate_adapters", return_value=[GPU, dict(OTHER, name="NVIDIA")]), \
                patch("app.gpu_check.engine_snapshot", side_effect=[{}, {counter(): 100}]):
            observe_inference(check, lambda: None)
        self.assertEqual(check["status"], "unverified")

    def test_completed_check_does_not_collect_again(self):
        check = {"status": "verified"}
        with patch("app.gpu_check.engine_snapshot") as snapshot:
            observe_inference(check, lambda: None)
        snapshot.assert_not_called()

    def test_counter_reset_does_not_count_as_activity(self):
        self.assertEqual(active_adapters({counter(): 100}, {counter(): 1}), {})

    def test_graphics_and_compute_aliases_are_accepted_but_copy_and_video_are_not(self):
        for engine in ("3D", "Compute_0", "COMPUTE_1", "Graphics", "Graphics_1", "CUDA"):
            with self.subTest(engine=engine):
                self.assertEqual(active_adapters({}, {counter(engine=engine): 17}), {GPU["luid"]: 17})
        for engine in ("Copy", "Copy_1", "VideoDecode", "VideoEncode", "LegacyOverlay",
                       "Unknown", "NotCompute", "GraphicsCopy", "Video3D"):
            with self.subTest(engine=engine):
                self.assertEqual(active_adapters({}, {counter(engine=engine): 17}), {})

    def test_reported_gtx1660_super_load_and_image_activity(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/gtx1660_gpu_counters.json").read_text())
        for sample in fixture["samples"]:
            with self.subTest(phase=sample["phase"]):
                check = self.check()
                check.update(phase=sample["phase"], expected_device=fixture["device"])
                infer = Mock(return_value="tags")
                with patch("app.dxgi.enumerate_adapters", return_value=[fixture["device"]]), \
                        patch("app.gpu_check.engine_snapshot", side_effect=[sample["before"], sample["after"]]):
                    self.assertEqual(observe_inference(check, infer), "tags")
                self.assertEqual(check["status"], "verified")
                self.assertEqual(len(check["observed_devices"]), 1)
                self.assertEqual(check["observed_devices"][0]["luid"], fixture["device"]["luid"])
                self.assertEqual(check["observed_devices"][0]["running_time_100ns"], sample["expected_ticks"])
                self.assertIn("graphics_1", check["message"])
                infer.assert_called_once()

    def test_graphics_on_another_adapter_is_mismatch_and_two_adapters_are_inconclusive(self):
        for after, status in [({counter("B", "Graphics_1"): 11}, "mismatch"),
                              ({counter(engine="Graphics_1"): 11, counter("B"): 12}, "unverified")]:
            with self.subTest(status=status):
                check = self.check()
                with patch("app.dxgi.enumerate_adapters", return_value=[GPU, OTHER]), \
                        patch("app.gpu_check.engine_snapshot", side_effect=[{}, after]):
                    observe_inference(check, lambda: None)
                self.assertEqual(check["status"], status)

    def test_unknown_engine_is_not_called_copy_only_or_used_to_verify_a_device(self):
        for after in [{counter(engine="VendorEngine"): 10},
                      {counter(engine="Graphics_1"): 10, counter("B", "VendorEngine"): 10}]:
            check = self.check()
            with patch("app.dxgi.enumerate_adapters", return_value=[GPU, OTHER]), \
                    patch("app.gpu_check.engine_snapshot", side_effect=[{}, after, after]):
                observe_inference(check, lambda: None)
            self.assertEqual(check["status"], "unverified")
            self.assertEqual(check["reason"], "unrecognized_engines")

    def test_snapshot_filters_exact_pid_despite_wql_wildcards_and_logs_raw_values(self):
        own = counter()
        rows = [{"Name": own.upper(), "RunningTime": "123"},
                {"Name": own.replace("pid_123_", "pid_1234_"), "RunningTime": "999"}]
        with patch("app.gpu_check.os.name", "nt"), patch("app.gpu_check.os.getpid", return_value=123), \
                patch("app.gpu_check.subprocess.check_output", return_value=json.dumps(rows).encode()), \
                self.assertLogs("app.gpu_check", level="INFO") as logs:
            self.assertEqual(engine_snapshot(), {own.lower(): 123})
        self.assertIn("own_rows=1", logs.output[0])
        self.assertIn(own.lower(), logs.output[0])

    def test_counter_command_error_is_in_log(self):
        error = subprocess.CalledProcessError(1, "powershell", stderr=b"Invalid class")
        with patch("app.gpu_check.os.name", "nt"), \
                patch("app.gpu_check.subprocess.check_output", side_effect=error), \
                self.assertLogs("app.gpu_check", level="WARNING") as logs:
            with self.assertRaises(subprocess.CalledProcessError):
                engine_snapshot()
        self.assertIn("Invalid class", logs.output[0])


if __name__ == "__main__":
    unittest.main()
