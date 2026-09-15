from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from app.gpu_check import session_check
from app.models.loader import LoadedModel, _preflight_model


class PreflightTests(unittest.TestCase):
    def model(self, kind="wd14"):
        session = Mock()
        session.get_providers.return_value = ["CPUExecutionProvider"]
        session.get_inputs.return_value = [SimpleNamespace(name="input")]
        session.run.return_value = [np.array([[0.1, 0.5]], dtype=np.float32)]
        model = LoadedModel("test", session, 64, "CPUExecutionProvider", kind=kind)
        model.device_check = session_check(session, "CPUExecutionProvider", None)
        return model

    def test_load_probe_uses_correct_model_input_layout(self):
        for kind, shape in [("wd14", (1, 64, 64, 3)), ("camie_v2", (1, 3, 64, 64))]:
            model = self.model(kind)
            _preflight_model(model)
            tensor = model.session.run.call_args.args[1]["input"]
            self.assertEqual(tensor.shape, shape)
            self.assertEqual(tensor.dtype, np.float32)
            self.assertEqual(model.device_check["preflight"]["phase"], "load")
            self.assertEqual(model.device_check["phase"], "image")

    def test_nonfinite_and_missing_outputs_fail_load(self):
        for outputs in [[], [np.array([])], [np.array([np.nan])], [np.array([np.inf])]]:
            model = self.model()
            model.session.run.return_value = outputs
            with self.assertRaisesRegex(RuntimeError, "自检失败"):
                _preflight_model(model)

    def test_wrong_device_is_rejected_before_probe(self):
        model = self.model()
        model.device_check.update(status="mismatch", message="wrong device")
        with self.assertRaisesRegex(RuntimeError, "wrong device"):
            _preflight_model(model)
        model.session.run.assert_not_called()

    def test_cpu_only_model_is_rejected_even_with_dml_registered(self):
        model = self.model()
        model.profile_enabled = True
        model.session.get_providers.return_value = ["DmlExecutionProvider", "CPUExecutionProvider"]
        model.session.get_provider_options.return_value = {}
        model.device_check = session_check(model.session, "DmlExecutionProvider", None)
        with patch("app.models.loader.observe_inference", side_effect=lambda check, run: run()), \
                patch("app.models.loader.finish_profile", return_value={"status": "cpu_only"}) as finish:
            with self.assertRaisesRegex(RuntimeError, "模型计算全部落在 CPU"):
                _preflight_model(model)
        finish.assert_called_once()
        self.assertFalse(model.profile_enabled)
        self.assertEqual(model.device_check["reason"], "cpu_only_execution")
        model.session.run.assert_called_once()

    def test_inference_failure_still_saves_and_stops_profile(self):
        model = self.model()
        model.profile_enabled = True
        model.session.run.side_effect = RuntimeError("driver failure")
        with patch("app.models.loader.finish_profile", return_value={"status": "unverified"}) as finish:
            with self.assertRaisesRegex(RuntimeError, "driver failure"):
                _preflight_model(model)
        finish.assert_called_once()
        self.assertFalse(model.profile_enabled)

    def test_profile_does_not_replace_unverified_physical_device_with_success(self):
        model = self.model()
        model.profile_enabled = True
        model.device_check.update(status="unverified", message="no GPU counters")
        with patch("app.models.loader.finish_profile", return_value={"status": "provider_observed"}):
            _preflight_model(model)
        self.assertEqual(model.device_check["preflight"]["status"], "unverified")
        self.assertEqual(model.device_check["preflight"]["execution_check"]["status"], "provider_observed")


if __name__ == "__main__":
    unittest.main()
