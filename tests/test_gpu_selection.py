import importlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app import hardware
from app.models import loader

DML = "DmlExecutionProvider"
CUDA = "CUDAExecutionProvider"
CPU = "CPUExecutionProvider"


class DeviceSelectionTests(unittest.TestCase):
    def test_dxgi_order_gaps_and_identical_cards_are_preserved(self):
        adapters = [
            {"id": 0, "name": "NVIDIA RTX 4050", "software": False},
            {"id": 1, "name": "Virtual Display", "software": False},
            {"id": 2, "name": "Intel UHD", "software": False},
            {"id": 3, "name": "NVIDIA RTX 4050", "software": False},
            {"id": 4, "name": "Microsoft Basic Render Driver", "software": True},
        ]
        with patch("app.dxgi.enumerate_adapters", return_value=adapters):
            devices = hardware.list_provider_gpus(DML)
            self.assertEqual([g["id"] for g in devices], [0, 2, 3])
            self.assertEqual(hardware.preferred_providers([DML, CUDA, CPU], 2),
                             [(DML, {"device_id": 2}), CPU])

    def test_failed_enumeration_does_not_guess_wmi_ids(self):
        with patch("app.dxgi.enumerate_adapters", side_effect=OSError("unavailable")):
            with self.assertLogs("app.hardware", level="WARNING"):
                with self.assertRaises(ValueError):
                    hardware.preferred_providers([DML, CPU], 0)

    def test_automatic_selection_uses_largest_memory_and_preserves_id(self):
        devices = [{"id": 0, "memory_bytes": 512 * 2**20, "name": "Intel"},
                   {"id": 3, "memory_bytes": 8 * 2**30, "name": "NVIDIA"}]
        with patch.object(hardware, "list_provider_gpus", return_value=devices):
            self.assertEqual(hardware.preferred_providers([CPU, CUDA, DML]),
                             [(DML, {"device_id": 3}), CPU])
            self.assertEqual(hardware.preferred_providers([CPU, CUDA, DML], 0),
                             [(DML, {"device_id": 0}), CPU])

    def test_automatic_selection_handles_no_devices_and_memory_ties(self):
        with patch.object(hardware, "list_provider_gpus", return_value=[]):
            self.assertEqual(hardware.preferred_providers([CPU]), [CPU])
        devices = [{"id": 2, "memory_bytes": 10}, {"id": 3, "memory_bytes": 10}]
        self.assertEqual(hardware.largest_gpu(devices)["id"], 2)

    def test_invalid_or_cpu_only_manual_selection_is_rejected(self):
        with patch.object(hardware, "list_provider_gpus", return_value=[]):
            for providers, device in [([DML, CPU], -1), ([CPU], 0), ([], 0)]:
                with self.subTest(providers=providers, device=device):
                    with self.assertRaises(ValueError):
                        hardware.preferred_providers(providers, device)

    def test_cuda_uses_runtime_order(self):
        torch = SimpleNamespace(
            version=SimpleNamespace(hip=None),
            cuda=SimpleNamespace(device_count=lambda: 1,
                                 get_device_name=lambda i: "NVIDIA RTX 4050",
                                 get_device_properties=lambda i: SimpleNamespace(total_memory=6000)),
        )
        with patch.dict("sys.modules", {"torch": torch}):
            self.assertEqual(hardware.list_provider_gpus(CUDA),
                             [{"id": 0, "name": "NVIDIA RTX 4050", "memory_bytes": 6000}])
            self.assertEqual(hardware.list_provider_gpus("ROCMExecutionProvider"), [])

    def test_hardware_ui_uses_dxgi_not_wmi_order(self):
        ort = SimpleNamespace(get_available_providers=lambda: [DML, CPU])
        devices = [{"id": 0, "name": "NVIDIA"}, {"id": 1, "name": "Intel"}]
        with patch.dict("sys.modules", {"onnxruntime": ort}), \
                patch.object(hardware, "list_windows_gpus", return_value=["Intel", "NVIDIA"]), \
                patch.object(hardware, "list_provider_gpus", return_value=devices), \
                patch("app.network.detect_region", return_value={"region": "global"}):
            self.assertEqual(hardware.detect_hardware()["gpus_indexed"], devices)


class DirectMLSessionTests(unittest.TestCase):
    def test_session_configuration_and_cpu_fallback(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                session = Mock()
                session.get_providers.return_value = [CPU] if fail else [DML, CPU]
                ort = SimpleNamespace(
                    get_available_providers=lambda: [DML, CPU],
                    SessionOptions=SimpleNamespace,
                    ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL="sequential"),
                    InferenceSession=Mock(side_effect=[RuntimeError("driver"), session]
                                          if fail else None, return_value=session),
                )
                with patch.dict("sys.modules", {"onnxruntime": ort}), \
                        patch.object(loader, "_current", None), \
                        patch.object(hardware, "list_provider_gpus", return_value=[]), \
                        patch.object(loader, "list_provider_gpus", return_value=[]), \
                        patch.object(loader, "log_gpu_environment"), \
                        patch.object(loader, "_download", return_value=[Path("model.onnx")]), \
                        patch.object(loader, "_build_wd14"), \
                        patch.object(loader, "enable_profile", return_value=False), \
                        patch.object(loader, "_preflight_model"), \
                        patch.object(loader, "model_kind", return_value="wd14"), \
                        self.assertLogs("app.models.loader", level="INFO"):
                    loader.load_model(next(iter(loader.MODEL_REGISTRY)))
                options = ort.InferenceSession.call_args_list[0].args[1]
                self.assertFalse(options.enable_mem_pattern)
                self.assertEqual(options.execution_mode, "sequential")
                if fail:
                    self.assertEqual(ort.InferenceSession.call_args.kwargs["providers"], [CPU])

    def test_both_model_types_hold_session_lock(self):
        module = importlib.import_module("app.models.interrogator")
        for kind, helper in [("wd14", "_interrogate_wd14"), ("camie_v2", "_interrogate_camie")]:
            model = loader.LoadedModel("test", object(), 448, DML, kind=kind)

            def infer(*args):
                self.assertTrue(model.run_lock.locked())
                return {}, {"tag": 1.0}

            with patch.object(module, helper, side_effect=infer):
                self.assertEqual(module.interrogate(model, None), ({}, {"tag": 1.0}))
                self.assertFalse(model.run_lock.locked())


if __name__ == "__main__":
    unittest.main()
