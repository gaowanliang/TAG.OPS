import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from starlette.testclient import TestClient

from app.dialogs import show_native_dialog
from app.jobs import Job
from app.web import create_app


class DialogRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app()[0], base_url="http://127.0.0.1:8765")
        self.addCleanup(self.client.close)

    def test_cancel_and_folder_path_are_returned_from_backend(self):
        for kind, result in [("confirm", {"accepted": False}), ("folder", {"path": None}),
                             ("folder", {"path": "D:\\图片"})]:
            with patch("app.dialogs.show_native_dialog", return_value=result) as show:
                response = self.client.post("/api/dialog", json={"kind": kind, "title": "测试"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), result)
            show.assert_called_once_with(kind, "测试", "", "")

    def test_foreign_origin_invalid_type_and_malformed_fields_never_open_dialog(self):
        with patch("app.dialogs.show_native_dialog") as show:
            response = self.client.post("/api/dialog", json={"kind": "confirm"},
                                        headers={"origin": "https://example.com"})
            self.assertEqual(response.status_code, 403)
            for body in [{"kind": "command"}, {"kind": "alert", "title": []}]:
                self.assertEqual(self.client.post("/api/dialog", json=body).status_code, 400)
            show.assert_not_called()

    def test_native_failure_does_not_report_acceptance(self):
        with patch("app.dialogs.show_native_dialog", side_effect=OSError("desktop unavailable")):
            response = self.client.post("/api/dialog", json={"kind": "confirm"})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("accepted", response.json())

    def test_categories_require_folder_jobs(self):
        for source, status in [("upload", 400), ("folder", 200)]:
            with patch("app.jobs.get", return_value=Job("test", 0, source=source)):
                response = self.client.get("/api/categorize?job_id=test")
            self.assertEqual(response.status_code, status)

    def test_job_status_exposes_load_and_image_checks(self):
        check = {"status": "verified", "preflight": {"status": "verified"}}
        with patch("app.jobs.get", return_value=Job("test", 0, device_check=check)):
            response = self.client.get("/api/status?id=test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["device_check"], check)

    def test_legacy_modals_remain_hidden_and_notice_is_visible(self):
        html = self.client.get("/").text
        self.assertIn('id="dialog-modal"', html)
        self.assertIn('id="browser-modal"', html)
        self.assertIn('data-i18n="info.folder_only"', html)


@unittest.skipUnless(os.name == "nt", "Native Windows bindings")
class WindowsDialogTests(unittest.TestCase):
    def test_messagebox_cancel_is_false_and_default_is_cancel(self):
        show = Mock(return_value=2)
        with patch("app.dialogs.ctypes.WinDLL", return_value=SimpleNamespace(MessageBoxW=show)):
            self.assertEqual(show_native_dialog("confirm", "标题", "内容"), {"accepted": False})
        self.assertTrue(show.call_args.args[3] & 0x100)

    def test_folder_picker_uses_shell_api_and_preserves_unicode(self):
        title = "中文 ' $(not-a-command) `test`"
        with patch("app.windows_shell.pick_folder", return_value="D:\\图片") as pick, \
                patch("subprocess.run") as run:
            self.assertEqual(show_native_dialog("folder", title, initial_path="D:\\图片"),
                             {"path": "D:\\图片"})
        pick.assert_called_once_with(title, "D:\\图片")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
