"""Tests for the MCP facade (apero mcp — JSON-RPC 2.0 over stdio, read-only)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aperio.mcp import handle_request, serve
from aperio.store import Project

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class McpProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_initialize_returns_server_info(self) -> None:
        response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["result"]["serverInfo"]["name"], "aperio")
        self.assertIn("protocolVersion", response["result"])

    def test_tools_list_exposes_read_only_tools(self) -> None:
        response = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in response["result"]["tools"]]
        self.assertEqual(
            names,
            ["aperio_next", "aperio_explain", "aperio_status", "aperio_lessons", "aperio_doctor"],
        )
        # No write tools: the facade must not carry mutation across the pipe.
        for tool in response["result"]["tools"]:
            self.assertNotIn("add", tool["name"])
            self.assertNotIn("run", tool["name"])
            self.assertNotIn("approve", tool["name"])

    def test_unknown_method_returns_method_not_found(self) -> None:
        response = handle_request({"jsonrpc": "2.0", "id": 3, "method": "nope"})
        self.assertEqual(response["error"]["code"], -32601)

    def test_unknown_tool_returns_invalid_params(self) -> None:
        response = handle_request(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "aperio_hack"}}
        )
        self.assertEqual(response["error"]["code"], -32602)

    def test_explain_call_without_a_live_project(self) -> None:
        # A project path that does not exist: explain still works, with no
        # live status attached (and never creates the project).
        missing = Path(self.temp.name) / "does-not-exist"
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "aperio_explain",
                    "arguments": {"topic": "review", "project": str(missing)},
                },
            }
        )
        text = response["result"]["content"][0]["text"]
        self.assertIn("WHAT IT CHECKS", text)
        self.assertNotIn("This project now:", text)
        self.assertFalse(missing.exists(), "explain must not create a project")

    def test_bad_topic_is_a_tool_error_not_a_protocol_error(self) -> None:
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "aperio_explain", "arguments": {"topic": "nonsense"}},
            }
        )
        self.assertTrue(response["result"]["isError"])
        self.assertIn("unknown topic", response["result"]["content"][0]["text"])

    def test_notification_yields_no_response(self) -> None:
        self.assertEqual(handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}), {})

    def test_malformed_json_gets_parse_error(self) -> None:
        import io

        stdin = io.StringIO("{not json}\n")
        stdout = io.StringIO()
        serve(stdin=stdin, stdout=stdout)
        response = json.loads(stdout.getvalue().splitlines()[0])
        self.assertEqual(response["error"]["code"], -32700)


class McpLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "proj"
        self.project = Project.init(self.root, "mcp-test")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_status_and_next_tools_over_a_live_project(self) -> None:
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "aperio_status", "arguments": {"project": str(self.root)}},
            }
        )
        payload = json.loads(response["result"]["content"][0]["text"])
        # Project.open resolves the root (macOS /var -> /private/var).
        self.assertEqual(Path(payload["project"]), self.root.resolve())
        self.assertEqual(payload["tasks"], [])

        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {"name": "aperio_next", "arguments": {"project": str(self.root)}},
            }
        )
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertIn("action", payload)

    def test_doctor_reports_malformed_state_as_unhealthy(self) -> None:
        # A host review caught doctor reporting presence only, while its
        # description promises parseable. A corrupted state file must be
        # reported unparseable, and a healthy file must carry its schema.
        (self.project.state / "queue.json").write_text("{corrupt", encoding="utf-8")
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": "aperio_doctor", "arguments": {"project": str(self.root)}},
            }
        )
        payload = json.loads(response["result"]["content"][0]["text"])
        by_name = {c["file"]: c for c in payload["checks"]}
        self.assertFalse(by_name["queue.json"]["parseable"])
        self.assertIn("error", by_name["queue.json"])
        self.assertTrue(by_name["project.json"]["parseable"])
        self.assertEqual(by_name["project.json"]["schema"], 1)

    def test_default_project_from_serve(self) -> None:
        # A host review caught the CLI --project being ignored when a tool
        # call omits its project argument.
        import io

        requests = "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "aperio_status", "arguments": {}}}),
            ]
        )
        stdin = io.StringIO(requests + "\n")
        stdout = io.StringIO()
        serve(stdin=stdin, stdout=stdout, default_project=str(self.root))
        payload = json.loads(json.loads(stdout.getvalue().splitlines()[0])["result"]["content"][0]["text"])
        self.assertEqual(Path(payload["project"]), self.root.resolve())

    def test_malformed_requests_do_not_kill_the_server(self) -> None:
        # A host review caught non-dict params and bad request shapes
        # reaching the handlers. Each malformed line must yield a JSON-RPC
        # error and the server must keep serving the next line.
        import io

        lines_in = "\n".join(
            [
                json.dumps({"jsonrpc": "1.0", "id": 1, "method": "initialize"}),
                json.dumps({"id": 2, "method": "initialize"}),
                json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": "not-an-object"}),
                json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": 42}}),
                json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "aperio_status", "arguments": "not-an-object"}}),
                json.dumps({"jsonrpc": "2.0", "id": 6, "method": "initialize"}),
            ]
        )
        stdin = io.StringIO(lines_in + "\n")
        stdout = io.StringIO()
        serve(stdin=stdin, stdout=stdout)
        lines = stdout.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 6, "every malformed line gets an error; the last line still succeeds")
        self.assertEqual(json.loads(lines[0])["error"]["code"], -32600)
        self.assertEqual(json.loads(lines[1])["error"]["code"], -32600)
        self.assertEqual(json.loads(lines[2])["error"]["code"], -32602)
        self.assertEqual(json.loads(lines[3])["error"]["code"], -32602)
        self.assertEqual(json.loads(lines[4])["error"]["code"], -32602)
        self.assertIn("serverInfo", json.loads(lines[5])["result"])

    def test_serve_over_real_stdio_subprocess(self) -> None:
        requests = "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "aperio_next", "arguments": {"project": str(self.root)}},
                    }
                ),
            ]
        )
        result = subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), "mcp"],
            input=requests,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(ROOT),
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 3)
        init = json.loads(lines[0])
        self.assertEqual(init["result"]["serverInfo"]["name"], "aperio")
        tools = json.loads(lines[1])
        self.assertEqual(len(tools["result"]["tools"]), 5)
        nxt = json.loads(lines[2])
        self.assertIn("action", json.loads(nxt["result"]["content"][0]["text"]))


if __name__ == "__main__":
    unittest.main()
