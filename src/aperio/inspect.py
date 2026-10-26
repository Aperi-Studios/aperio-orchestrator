"""Read-only inspection of a project folder or a public URL.

This module records facts and evidence references. It does not answer owner
questions, install packages, run builds, or write into the inspected target.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .model import utc_now
from .store import Project

SKIP_DIRS = {
    ".git",
    ".aperio",
    "node_modules",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "dist",
    "build",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
    ".idea",
    ".vscode",
    "target",
    "vendor",
}
MAX_FILES = 5000
MAX_URL_BYTES = 2_000_000
MAX_ROUTES = 80


class InspectionError(RuntimeError):
    """The path or URL is unsafe, unreadable, or invalid."""


class _HtmlFacts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.description = ""
        self.canonical = ""
        self.robots = ""
        self.lang = ""
        self.h1: list[str] = []
        self.links = 0
        self.images = 0
        self.images_without_alt = 0
        self.forms = 0
        self.scripts = 0
        self._in_title = False
        self._in_h1 = False
        self._h1_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag == "html" and values.get("lang"):
            self.lang = values["lang"]
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
            self._h1_parts = []
        elif tag == "meta":
            name = values.get("name", "").lower()
            if name == "description":
                self.description = values.get("content", "")
            elif name == "robots":
                self.robots = values.get("content", "")
        elif tag == "link":
            rel = values.get("rel", "").lower()
            if "canonical" in rel:
                self.canonical = values.get("href", "")
            if "stylesheet" in rel or "icon" in rel:
                self.links += 1
        elif tag == "a":
            self.links += 1
        elif tag == "img":
            self.images += 1
            if "alt" not in values:
                self.images_without_alt += 1
        elif tag == "form":
            self.forms += 1
        elif tag == "script":
            self.scripts += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            if self._h1_parts:
                self.h1.append(" ".join(self._h1_parts))
            self._h1_parts = []
            self._in_h1 = False

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        if self._in_title:
            self.title = (self.title + " " + value).strip()
        if self._in_h1:
            self._h1_parts.append(value)


def parse_html(text: str, base_url: str = "") -> dict[str, Any]:
    parser = _HtmlFacts()
    try:
        parser.feed(text)
    except Exception as exc:  # pragma: no cover - HTMLParser is tolerant
        raise InspectionError(f"could not parse HTML: {exc}") from exc
    canonical = parser.canonical
    if canonical and base_url:
        canonical = urllib.parse.urljoin(base_url, canonical)
    return {
        "title": parser.title,
        "description": parser.description,
        "canonical": canonical,
        "robots": parser.robots,
        "lang": parser.lang,
        "h1": parser.h1[:10],
        "links": parser.links,
        "images": parser.images,
        "images_without_alt": parser.images_without_alt,
        "forms": parser.forms,
        "scripts": parser.scripts,
        "base_url": base_url,
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _env_names(path: Path) -> list[str]:
    names: list[str] = []
    if path.is_symlink():
        return names
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key = line.split("=", 1)[0].strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                names.append(key)
    except (OSError, UnicodeError):
        return []
    return sorted(dict.fromkeys(names))[:50]


def _detect_stack(root: Path) -> dict[str, Any]:
    stack: list[str] = []
    scripts: dict[str, str] = {}
    package_manager = ""
    dependencies: list[str] = []
    package = _read_json(root / "package.json")
    if package is not None:
        scripts = {
            str(key): str(value)
            for key, value in (package.get("scripts") or {}).items()
            if isinstance(key, str) and isinstance(value, str)
        }
        all_deps = {}
        for key in ("dependencies", "devDependencies"):
            value = package.get(key)
            if isinstance(value, dict):
                all_deps.update({str(k): str(v) for k, v in value.items()})
        dependencies = sorted(all_deps)
        known = {
            "next": "Next.js",
            "react": "React",
            "vue": "Vue",
            "nuxt": "Nuxt",
            "astro": "Astro",
            "svelte": "Svelte",
            "@angular/core": "Angular",
            "@sveltejs/kit": "SvelteKit",
            "express": "Express",
            "fastify": "Fastify",
            "hono": "Hono",
            "vite": "Vite",
            "shopify": "Shopify",
            "stripe": "Stripe",
            "@payloadcms/db-postgres": "Payload CMS",
            "contentful": "Contentful",
            "sanity": "Sanity",
            "directus": "Directus",
        }
        for dependency, label in known.items():
            if dependency in all_deps and label not in stack:
                stack.append(label)
        package_manager = str(package.get("packageManager") or "")
        if not package_manager:
            for lock, name in (
                ("pnpm-lock.yaml", "pnpm"),
                ("yarn.lock", "yarn"),
                ("package-lock.json", "npm"),
                ("bun.lockb", "bun"),
            ):
                if (root / lock).is_file():
                    package_manager = name
                    break
    for marker, label in (
        ("pyproject.toml", "Python"),
        ("requirements.txt", "Python"),
        ("setup.py", "Python"),
        ("manage.py", "Django"),
        ("Cargo.toml", "Rust"),
        ("go.mod", "Go"),
        ("composer.json", "PHP"),
        ("Gemfile", "Ruby"),
    ):
        if (root / marker).is_file() and label not in stack:
            stack.append(label)
    if (root / "manage.py").is_file() and "Django" not in stack:
        stack.append("Django")
    requirements = root / "requirements.txt"
    if requirements.is_file():
        try:
            text = requirements.read_text(encoding="utf-8").lower()
        except (OSError, UnicodeError):
            text = ""
        for token, label in (
            ("fastapi", "FastAPI"),
            ("flask", "Flask"),
            ("django", "Django"),
            ("streamlit", "Streamlit"),
        ):
            if token in text and label not in stack:
                stack.append(label)
    return {
        "stack": stack,
        "scripts": scripts,
        "package_manager": package_manager,
        "dependencies": dependencies[:100],
    }


def _detect_cms_or_commerce(dependencies: list[str], stack: list[str]) -> dict[str, list[str]]:
    text = " ".join(dependencies + stack).lower()
    cms = []
    commerce = []
    for token, label in (
        ("payload", "Payload"),
        ("contentful", "Contentful"),
        ("sanity", "Sanity"),
        ("directus", "Directus"),
        ("strapi", "Strapi"),
        ("wordpress", "WordPress"),
        ("shopify", "Shopify"),
        ("woocommerce", "WooCommerce"),
        ("stripe", "Stripe"),
        ("medusa", "Medusa"),
    ):
        if token in text:
            if token in {"shopify", "woocommerce", "stripe", "medusa"}:
                commerce.append(label)
            else:
                cms.append(label)
    return {"cms": sorted(set(cms)), "commerce": sorted(set(commerce))}


def _html_file(root: Path) -> Path | None:
    for relative in ("index.html", "public/index.html", "src/index.html", "home.html"):
        path = root / relative
        if path.is_file() and not path.is_symlink():
            return path
    return None


def _routes(root: Path) -> list[str]:
    routes: list[str] = []
    for base in ("pages", "src/pages", "app", "src/app", "routes", "src/routes"):
        directory = root / base
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.is_dir() or path.is_symlink():
                continue
            if path.suffix.lower() not in {".html", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".astro", ".py"}:
                continue
            routes.append(path.relative_to(root).as_posix())
            if len(routes) >= MAX_ROUTES:
                return sorted(routes)
    return sorted(routes)


def _git_facts(root: Path) -> dict[str, Any]:
    if not (root / ".git").exists() or shutil.which("git") is None:
        return {"is_repo": False}
    facts: dict[str, Any] = {"is_repo": True}
    base = [
        "git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.pager=cat",
        "-c",
        "diff.external=",
        "-C",
        str(root),
    ]
    for key, args in (
        ("branch", ["rev-parse", "--abbrev-ref", "HEAD"]),
        ("remote_count", ["remote"]),
        ("dirty_count", ["status", "--porcelain"]),
    ):
        try:
            result = subprocess.run(base + args, check=False, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0:
            continue
        value = result.stdout.strip()
        if key == "remote_count" or key == "dirty_count":
            facts[key] = len([line for line in value.splitlines() if line.strip()])
        elif value:
            facts[key] = value
    return facts


def inspect_path(root: str | Path) -> dict[str, Any]:
    path = Path(root).expanduser().resolve()
    if not path.is_dir():
        raise InspectionError(f"not a directory: {path}")
    files = 0
    total_bytes = 0
    truncated = False
    top_level: list[str] = []
    try:
        top_level = sorted(item.name for item in path.iterdir() if item.name not in SKIP_DIRS)
    except OSError as exc:
        raise InspectionError(f"cannot read directory: {path}: {exc}") from exc
    for current, dirnames, filenames in os.walk(path, followlinks=False):
        dirnames[:] = [
            name for name in dirnames if name not in SKIP_DIRS and not (Path(current) / name).is_symlink()
        ]
        for name in filenames:
            file_path = Path(current) / name
            if file_path.is_symlink():
                continue
            files += 1
            try:
                total_bytes += file_path.stat().st_size
            except OSError:
                pass
            if files >= MAX_FILES:
                truncated = True
                break
        if files >= MAX_FILES:
            break
    stack_facts = _detect_stack(path)
    dependencies = stack_facts["dependencies"]
    cms_commerce = _detect_cms_or_commerce(dependencies, stack_facts["stack"])
    html_file = _html_file(path)
    html_facts: dict[str, Any] = {}
    if html_file is not None:
        try:
            html_facts = parse_html(html_file.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            html_facts = {}
    tests = any((path / name).exists() for name in ("tests", "test", "__tests__")) or any(
        child.name.startswith("test_") or ".test." in child.name or ".spec." in child.name
        for child in path.rglob("*")
        if child.is_file() and not child.is_symlink()
    )
    docs = [name for name in ("README.md", "README.rst", "docs") if (path / name).exists()]
    ci = (path / ".github" / "workflows").is_dir()
    deployment = [
        name
        for name in ("vercel.json", "netlify.toml", "fly.toml", "render.yaml", "Dockerfile", "wrangler.toml", "docker-compose.yml")
        if (path / name).exists()
    ]
    env_files = [
        name for name in (".env.example", ".env.sample", ".env.template") if (path / name).is_file()
    ]
    env_names: list[str] = []
    if env_files:
        env_names = _env_names(path / env_files[0])
    return {
        "kind": "folder",
        "captured_at": utc_now(),
        "root": str(path),
        "name": path.name,
        "top_level": top_level[:80],
        "files": files,
        "truncated": truncated,
        "bytes": total_bytes,
        "stack": stack_facts["stack"],
        "scripts": stack_facts["scripts"],
        "package_manager": stack_facts["package_manager"],
        "dependencies": dependencies,
        "cms": cms_commerce["cms"],
        "commerce": cms_commerce["commerce"],
        "routes": _routes(path),
        "tests": bool(tests),
        "docs": docs,
        "ci": ci,
        "deployment": deployment,
        "env_files": env_files,
        "env_names": env_names,
        "html": html_facts,
        "git": _git_facts(path),
        "limits": [
            "Inspection is read-only but does not prove behavior.",
            "No files outside the target are read.",
            "No dependency is installed, built, or executed.",
        ],
    }


def _private_host(host: str) -> bool:
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError as exc:
        raise InspectionError(f"cannot resolve host: {host}: {exc}") from exc
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return True
        if not ip.is_global:
            return True
    return False


def _validate_url(url: str, allow_private: bool) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise InspectionError(f"URL must be http or https with a hostname: {url}")
    if parsed.username or parsed.password:
        raise InspectionError("URL must not contain credentials")
    if not allow_private and _private_host(parsed.hostname):
        raise InspectionError("refusing a private, loopback, or non-public URL")
    return parsed


def _display_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if not parsed.query:
        return url
    pairs = []
    for item in parsed.query.split("&"):
        key = item.split("=", 1)[0]
        pairs.append(f"{key}=[redacted]" if key else "[redacted]")
    return urllib.parse.urlunsplit(parsed._replace(query="&".join(pairs)))


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allow_private: bool) -> None:
        self.allow_private = allow_private

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        absolute = urllib.parse.urljoin(req.full_url, newurl)
        _validate_url(absolute, self.allow_private)
        return super().redirect_request(req, fp, code, msg, headers, absolute)


def inspect_url(url: str, allow_private: bool = False) -> dict[str, Any]:
    _validate_url(url, allow_private)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Aperio-Inspect/2.0 (read-only)"},
        method="GET",
    )
    opener = urllib.request.build_opener(_CheckedRedirect(allow_private))
    try:
        with opener.open(request, timeout=12) as response:
            body = response.read(MAX_URL_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                text = body.decode(charset, errors="replace")
            except LookupError:
                text = body.decode("utf-8", errors="replace")
            headers = response.headers
            final_url = response.geturl()
            status = response.status
    except urllib.error.HTTPError as exc:
        raise InspectionError(f"HTTP {exc.code} for {url}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise InspectionError(f"cannot fetch {url}: {exc}") from exc
    facts = parse_html(text, final_url)
    _validate_url(final_url, allow_private)
    security_headers = {
        key.lower(): headers.get(key, "")
        for key in (
            "Strict-Transport-Security",
            "Content-Security-Policy",
            "X-Frame-Options",
            "X-Content-Type-Options",
        )
    }
    return {
        "kind": "url",
        "captured_at": utc_now(),
        "url": _display_url(url),
        "final_url": _display_url(final_url),
        "status": status,
        "content_type": headers.get("Content-Type", ""),
        "server": headers.get("Server", ""),
        "security_headers": security_headers,
        "html": facts,
        "limits": [
            "Inspection is a single read-only GET; it does not test interactions or rendering.",
            "Only a public URL is fetched; private and loopback hosts are refused.",
            "Redirect targets are revalidated before each hop; DNS rebinding is not fully prevented.",
        ],
    }


def collect(project: Project, url: str | None = None, allow_private: bool = False) -> dict[str, Any]:
    folder = inspect_path(project.root)
    data: dict[str, Any] = {
        "kind": "folder+url" if url else "folder",
        "captured_at": utc_now(),
        "folder": folder,
        "url": None,
        "limits": list(folder.get("limits", [])),
    }
    if url:
        try:
            data["url"] = inspect_url(url, allow_private=allow_private)
            data["limits"].extend(data["url"].get("limits", []))
        except InspectionError as exc:
            data["url"] = {"error": str(exc)}
            data["limits"].append("The URL inspection failed; folder facts are still recorded.")
            project.save_inspection(data)
            raise
    project.save_inspection(data)
    return data


def hints(project: Project, question_id: str) -> list[str]:
    data = project.inspection()
    if not data:
        return []
    folder = data.get("folder") or {}
    url = data.get("url") or {}
    result: list[str] = []
    if question_id == "evidence":
        if folder.get("files"):
            result.append("repo — the folder contains files")
        if url.get("status"):
            result.append("url — the URL was reachable during inspection")
    elif question_id == "constraints":
        if folder.get("stack"):
            result.append("stack — detected: " + ", ".join(folder["stack"][:5]))
        if folder.get("deployment"):
            result.append("hosting — deployment markers: " + ", ".join(folder["deployment"][:5]))
    elif question_id == "labels":
        if folder.get("cms"):
            result.append("cms — detected: " + ", ".join(folder["cms"]))
        if folder.get("commerce"):
            result.append("commerce — detected: " + ", ".join(folder["commerce"]))
        if url:
            result.append("seo — a public URL was inspected")
        if folder.get("git", {}).get("is_repo"):
            result.append("change — an existing git repository was found")
        else:
            result.append("new — no git repository was found")
    elif question_id == "name" and folder.get("name"):
        result.append(f"name — folder is named {folder['name']}")
    return result


def format_report(data: dict[str, Any]) -> str:
    folder = data.get("folder") or {}
    url = data.get("url") or {}
    lines = ["# Read-only inspection", ""]
    if folder:
        lines.extend(
            [
                f"Folder: {folder.get('root', '')}",
                f"Files: {folder.get('files', 0)}",
                f"Stack: {', '.join(folder.get('stack', [])) or 'not detected'}",
                f"Package manager: {folder.get('package_manager') or 'not detected'}",
                f"Tests: {'yes' if folder.get('tests') else 'not detected'}",
                f"Docs: {', '.join(folder.get('docs', [])) or 'not detected'}",
                f"CI: {'yes' if folder.get('ci') else 'not detected'}",
                f"Deployment: {', '.join(folder.get('deployment', [])) or 'not detected'}",
                f"Routes: {len(folder.get('routes', []))}",
            ]
        )
        if folder.get("env_names"):
            lines.append("Env names: " + ", ".join(folder["env_names"]))
    if url:
        html = url.get("html") or {}
        lines.extend(
            [
                "",
                f"URL: {url.get('final_url', '')}",
                f"Status: {url.get('status', '')}",
                f"Title: {html.get('title', '') or 'missing'}",
                f"Description: {html.get('description', '') or 'missing'}",
                f"H1: {', '.join(html.get('h1', [])) or 'missing'}",
                f"Lang: {html.get('lang', '') or 'missing'}",
                f"Images without alt: {html.get('images_without_alt', 0)}",
                f"Canonical: {html.get('canonical', '') or 'missing'}",
            ]
        )
    lines.extend(["", "Limits:"])
    lines.extend(f"- {limit}" for limit in data.get("limits", []))
    return "\n".join(lines)
