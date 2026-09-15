import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.ort_check import enable_profile, finish_profile, summarize_profile

DML = "DmlExecutionProvider"
CPU = "CPUExecutionProvider"
RUN = {"cat": "Session", "name": "model_run"}


def node(provider=CPU, op="MatMul", name="test_kernel_time"):
    return {"cat": "Node", "name": name, "dur": 5, "args": {"provider": provider, "op_name": op}}


class ExecutionProfileTests(unittest.TestCase):
    def test_mixed_execution_counts_ops_without_claiming_physical_gpu_identity(self):
        report = summarize_profile([RUN, node(DML), node(DML), node(CPU, "Shape"),
                                    node(CPU, "Shape", "test_fence_before")], DML)
        self.assertEqual(report["status"], "provider_observed")
        self.assertEqual(report["providers"][DML]["ops"], {"MatMul": 2})
        self.assertEqual(report["providers"][CPU]["node_count"], 1)
        self.assertEqual(report["cpu_compute_ops"], {})

    def test_registered_dml_or_copy_nodes_cannot_hide_cpu_only_execution(self):
        report = summarize_profile([RUN, node(CPU), node(DML, "MemcpyFromHost")], DML)
        self.assertEqual(report["status"], "cpu_only")
        self.assertEqual(report["cpu_compute_ops"], {"MatMul": 1})

    def test_missing_incomplete_or_unknown_evidence_never_proves_cpu_fallback(self):
        for events in [[], [RUN], [node(CPU)], [RUN, node(None)],
                       [RUN, node(CPU), node(None)], [RUN, node(DML, "MemcpyFromHost")]]:
            with self.subTest(events=events):
                self.assertEqual(summarize_profile(events, DML)["status"], "unverified")

    def test_profile_is_persisted_and_recording_stopped(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "载入.json"
            path.write_text(json.dumps([RUN, node(DML)]), encoding="utf-8")
            session = Mock(end_profiling=Mock(return_value=str(path)))
            report = finish_profile(session, DML)
            self.assertEqual(report["status"], "provider_observed")
            self.assertEqual(report["profile_file"], str(path))
            self.assertTrue(path.exists())
            session.end_profiling.assert_called_once()

    def test_bad_profile_does_not_claim_fallback_or_raise(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text("incomplete", encoding="utf-8")
            session = Mock(end_profiling=Mock(return_value=str(path)))
            with self.assertLogs("app.ort_check", level="WARNING"):
                self.assertEqual(finish_profile(session, DML)["status"], "unavailable")

    def test_profile_prefix_is_unique_under_logs(self):
        with TemporaryDirectory() as folder, patch("app.ort_check.LOG_DIR", Path(folder)):
            first, second = SimpleNamespace(), SimpleNamespace()
            self.assertTrue(enable_profile(first))
            self.assertTrue(enable_profile(second))
            self.assertTrue(first.enable_profiling)
            self.assertEqual(Path(first.profile_file_prefix).parent, Path(folder) / "ort-profiles")
            self.assertNotEqual(first.profile_file_prefix, second.profile_file_prefix)


if __name__ == "__main__":
    unittest.main()
