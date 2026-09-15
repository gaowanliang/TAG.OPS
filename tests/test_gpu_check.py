import unittest
from unittest.mock import Mock, patch

from app.gpu_check import active_adapters, observe_inference, session_check

CUDA = "CUDAExecutionProvider"
CPU = "CPUExecutionProvider"
GPU = {"id": 2, "name": "NVIDIA", "luid": "00000000:0000000a"}
OTHER = {"id": 0, "name": "Intel", "luid": "00000000:0000000b"}


def counter(luid="A", engine="3D"):
    return f"pid_123_luid_0x00000000_0x0000000{luid}_phys_0_eng_0_engtype_{engine}"


class GPUCheckTests(unittest.TestCase):
    def check(self):
        session = Mock()
        session.get_providers.return_value = [CUDA, CPU]
        session.get_provider_options.return_value = {CUDA: {"device_id": "2"}}
        return session_check(session, CUDA, GPU)

    def test_configuration_alone_never_verifies_activity(self):
        check = self.check()
        self.assertEqual(check["status"], "pending")
        self.assertEqual(check["reported_device_id"], 2)

    def test_cpu_fallback_and_wrong_runtime_device(self):
        session = Mock()
        session.get_providers.return_value = [CPU]
        self.assertEqual(session_check(session, CUDA, GPU)["status"], "fallback")
        session.get_providers.return_value = [CUDA, CPU]
        session.get_provider_options.return_value = {CUDA: {"device_id": "0"}}
        self.assertEqual(session_check(session, CUDA, GPU)["status"], "mismatch")

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
                        patch("app.gpu_check.engine_snapshot", side_effect=[{counter(): 100}, after]):
                    self.assertEqual(observe_inference(check, infer), "tags")
                self.assertEqual(check["status"], expected)
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


if __name__ == "__main__":
    unittest.main()
