from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request

from aperio.discovery import answer_question
from aperio.inspect import (
    InspectionError,
    _CheckedRedirect,
    _display_url,
    collect,
    hints,
    inspect_path,
    inspect_url,
    parse_html,
)
from aperio.store import Project

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class HtmlHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = (
            b"<!doctype html><html lang=\"en\"><head><title>Demo</title>"
            b"<meta name=\"description\" content=\"A demo\">"
            b"<link rel=\"canonical\" href=\"https://example.com/\"></head>"
            b"<body><h1>Hello</h1><a href=\"/x\">x</a><img src=\"a.png\"><form></form></body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class InspectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-inspect-")
        self.root = Path(self.temp.name) / "project"
        self.project = Project.init(self.root, name="inspect-test")
        (self.root / "src" / "pages").mkdir(parents=True)
        (self.root / "tests").mkdir()
        (self.root / ".github" / "workflows").mkdir(parents=True)
        (self.root / "package.json").write_text(
            json.dumps(
                {
                    "name": "demo",
                    "packageManager": "pnpm@9",
                    "scripts": {"build": "next build", "test": "vitest"},
                    "dependencies": {"next": "15", "react": "19", "stripe": "1", "sanity": "3"},
                    "devDependencies": {"vitest": "2"},
                }
            ),
            encoding="utf-8",
        )
        (self.root / "src" / "pages" / "index.tsx").write_text("export default function Page() {}\n")
        (self.root / "tests" / "test_demo.py").write_text("def test_demo():\n    pass\n")
        (self.root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")
        (self.root / "vercel.json").write_text("{}\n")
        (self.root / "README.md").write_text("# Demo\n")
        (self.root / ".env.example").write_text("API_KEY=do-not-read\n")
        (self.root / "index.html").write_text(
            '<!doctype html><html lang="en"><head><title>Demo Store</title>'
            '<meta name="description" content="A store"></head>'
            '<body><h1>Welcome</h1><img src="x.png"></body></html>'
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_folder_inspection_detects_stack_and_evidence(self) -> None:
        data = inspect_path(self.root)
        self.assertEqual(data["kind"], "folder")
        self.assertIn("Next.js", data["stack"])
        self.assertIn("React", data["stack"])
        self.assertIn("Stripe", data["commerce"])
        self.assertIn("Sanity", data["cms"])
        self.assertEqual(data["package_manager"], "pnpm@9")
        self.assertTrue(data["tests"])
        self.assertTrue(data["ci"])
        self.assertIn("vercel.json", data["deployment"])
        self.assertEqual(data["html"]["title"], "Demo Store")
        self.assertEqual(data["env_names"], ["API_KEY"])
        self.assertNotIn("do-not-read", json.dumps(data))

    def test_symlinked_index_is_not_read(self) -> None:
        secret = self.root.parent / "secret.html"
        secret.write_text("<html><title>SECRET</title></html>", encoding="utf-8")
        (self.root / "index.html").unlink()
        (self.root / "index.html").symlink_to(secret)
        data = inspect_path(self.root)
        self.assertNotIn("SECRET", json.dumps(data))
        self.assertNotIn("title", data["html"])

    def test_redirect_to_private_host_is_refused(self) -> None:
        request = Request("https://example.com/")
        with self.assertRaises(InspectionError):
            _CheckedRedirect(False).redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "http://127.0.0.1/secret",
            )

    def test_symlinked_package_json_is_not_read(self) -> None:
        secret = self.root.parent / "secret-package.json"
        secret.write_text('{"scripts":{"evil":"TOPSECRET"}}', encoding="utf-8")
        (self.root / "package.json").unlink()
        (self.root / "package.json").symlink_to(secret)
        data = inspect_path(self.root)
        self.assertNotIn("TOPSECRET", json.dumps(data))
        self.assertNotIn("evil", data["scripts"])

    def test_tests_detection_ignores_skipped_dirs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aperio-inspect-skip-") as name:
            root = Path(name)
            (root / "node_modules" / "pkg").mkdir(parents=True)
            (root / "node_modules" / "pkg" / "test_fake.js").write_text("x", encoding="utf-8")
            data = inspect_path(root)
            self.assertFalse(data["tests"])

    def test_corrupt_inspection_does_not_break_hints(self) -> None:
        (self.root / ".aperio" / "inspection.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(hints(self.project, "evidence"), [])

    def test_collect_and_hints(self) -> None:
        collect(self.project)
        evidence = hints(self.project, "evidence")
        labels = hints(self.project, "labels")
        constraints = hints(self.project, "constraints")
        self.assertTrue(any(item.startswith("repo") for item in evidence))
        self.assertTrue(any(item.startswith("commerce") for item in labels))
        self.assertTrue(any(item.startswith("stack") for item in constraints))
        self.assertTrue((self.root / ".aperio" / "inspection.json").is_file())

    def test_html_parser(self) -> None:
        facts = parse_html(
            '<html lang="en"><head><title>T</title><meta name="description" content="D">'
            '<link rel="canonical" href="/c"></head><body><h1>H</h1>'
            '<img src="x"><img src="y" alt="ok"><form></form></body></html>'
        )
        self.assertEqual(facts["title"], "T")
        self.assertEqual(facts["description"], "D")
        self.assertEqual(facts["canonical"], "/c")
        self.assertEqual(facts["h1"], ["H"])
        self.assertEqual(facts["images_without_alt"], 1)
        self.assertEqual(facts["forms"], 1)

    def test_html_parser_handles_inline_h1_and_decorative_alt(self) -> None:
        facts = parse_html(
            '<link rel="canonical" href="/x"><h1>Hello <em>world</em></h1>'
            '<img src="decorative.png" alt="">',
            base_url="https://example.com/page",
        )
        self.assertEqual(facts["h1"], ["Hello world"])
        self.assertEqual(facts["images_without_alt"], 0)
        self.assertEqual(facts["canonical"], "https://example.com/x")

    def test_url_rejects_credentials_and_redacts_query(self) -> None:
        with self.assertRaises(InspectionError):
            inspect_url("https://user:pass@example.com/")
        self.assertEqual(
            _display_url("https://example.com/page?token=SECRET&x=1"),
            "https://example.com/page?token=[redacted]&x=[redacted]",
        )

    def test_collect_saves_folder_when_url_fails(self) -> None:
        with self.assertRaises(InspectionError):
            collect(self.project, url="http://127.0.0.1:1/")
        data = self.project.inspection()
        assert data is not None
        self.assertEqual(data["folder"]["kind"], "folder")
        self.assertIn("error", data["url"])

    def test_url_inspection_and_private_refusal(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), HtmlHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/"
            with self.assertRaises(InspectionError):
                inspect_url(url)
            facts = inspect_url(url, allow_private=True)
            self.assertEqual(facts["status"], 200)
            self.assertEqual(facts["html"]["title"], "Demo")
            self.assertEqual(facts["html"]["h1"], ["Hello"])
            self.assertEqual(facts["html"]["images_without_alt"], 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_cli_inspect_and_hint_payload(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        inspect_cmd = subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), "inspect", "--json"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            timeout=30,
        )
        self.assertEqual(inspect_cmd.returncode, 0, inspect_cmd.stderr)
        self.assertIn("Next.js", inspect_cmd.stdout)
        answer_question(self.project, "idea", text="A store")
        answer_question(self.project, "users", text="Shoppers")
        next_cmd = subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), "discover", "next", "--json"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            timeout=30,
        )
        self.assertEqual(next_cmd.returncode, 0, next_cmd.stderr)
        payload = json.loads(next_cmd.stdout)
        self.assertIn("hints", payload["question"])


if __name__ == "__main__":
    unittest.main()
