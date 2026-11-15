"""启动器回归：这些分支只在真机上才走得到，必须锁住。

重点不是“能启动”，而是异常路径不出洋相：
占用端口不能硬崩、非交互环境不能自作主张杀进程、中文 Windows 的
netstat 输出不能解坏（这一条曾真实踩过）。
"""

from __future__ import annotations

import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import launch  # noqa: E402


class LauncherOptionsTest(unittest.TestCase):
    def test_defaults(self):
        port, host, browser, restart = launch._resolve_options([])
        self.assertEqual(port, launch.DEFAULT_PORT)
        self.assertEqual(host, launch.DEFAULT_HOST)
        self.assertTrue(browser)
        self.assertFalse(restart)

    def test_flags(self):
        port, _, browser, restart = launch._resolve_options(
            ["--port", "9123", "--no-browser", "--restart"]
        )
        self.assertEqual(port, 9123)
        self.assertFalse(browser)
        self.assertTrue(restart)

    def test_help_exits_zero(self):
        for flag in ("--help", "-h", "/?"):
            with self.assertRaises(SystemExit) as ctx:
                launch._resolve_options([flag])
            self.assertEqual(ctx.exception.code, 0)

    def test_bad_port_rejected(self):
        with self.assertRaises(SystemExit) as ctx:
            launch._resolve_options(["--port", "abc"])
        self.assertEqual(ctx.exception.code, 2)
        with self.assertRaises(SystemExit) as ctx:
            launch._resolve_options(["--port"])
        self.assertEqual(ctx.exception.code, 2)


class DecodeTest(unittest.TestCase):
    def test_gbk_netstat_output(self):
        """中文 Windows 的 netstat 输出是 GBK；按 UTF-8 硬解会抛异常。"""

        raw = "  TCP    0.0.0.0:8770   0.0.0.0:0   LISTENING   43152\r\n".encode("gbk")
        self.assertIn("LISTENING", launch._decode(raw))

    def test_broken_bytes_never_raise(self):
        self.assertIsInstance(launch._decode(b"\xff\xfe\xbb"), str)


class PortProbeTest(unittest.TestCase):
    def setUp(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]

    def tearDown(self):
        self.sock.close()

    def test_detects_busy_port(self):
        self.assertTrue(launch._port_open("127.0.0.1", self.port))

    def test_occupied_port_by_other_app_returns_one(self):
        """端口被别人占用且不是本工作台时必须明确失败，不能继续启动。"""

        code = launch.main(["--port", str(self.port), "--no-browser"])
        self.assertEqual(code, 1)

    def test_listening_pids_is_list(self):
        self.assertIsInstance(launch._listening_pids(self.port), list)


class DependencyProbeTest(unittest.TestCase):
    def test_core_deps_present_in_this_environment(self):
        self.assertEqual(launch._missing_core(), [])

    def test_missing_optional_detected(self):
        """可选依赖与必需依赖必须分开，否则启动器会把 torch 也拖进来。"""

        core = {name for _, name in launch.CORE_DEPS}
        optional = {name for _, name in launch.OPTIONAL_DEPS}
        self.assertFalse(core & optional)

    def test_requirements_file_exists(self):
        self.assertTrue(launch.REQUIREMENTS.exists())


if __name__ == "__main__":
    unittest.main()
