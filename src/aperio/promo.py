"""The promo generator: a launch-video plan built from a completed task's evidence.

``build_promo`` reads a done task's recorded evidence — the plan, the changed
files, the acceptance checks, the signed review — and drafts the artifacts a
motion build needs per docs/MOTION.md: a shot sheet whose times sum to the
declared runtime, a closed color script, and a full promo plan JSON (an HTML
composition under the determinism contract plus a render step and
machine-checkable acceptance).

Aperio generates the PLAN; it does not render. The promo plan is an ordinary
Aperio plan: it goes through the same approval gate, runs under the same
bounds, and its acceptance checks (lint, validate, times-sum, artifact
exists) are enforced the same way. Rendering itself requires the HyperFrames
toolchain, which the owner installs through `apero tool` — never a core
dependency.
"""

from __future__ import annotations

import json
from typing import Any

from .store import Project


class PromoError(ValueError):
    """The task is not eligible for a promo, or the draft is invalid."""


PROMO_PATHS = ["promo/"]
PALETTE = {
    "bg": "#0b0e14",
    "ink": "#e8ecf4",
    "accent": "#5b8cff",
    "muted": "#8a93a6",
}


def _changed_files(project: Project, task_id: str) -> list[str]:
    changed: list[str] = []
    for row in project.evidence_readonly(task_id):
        rows = row.get("changed_files")
        if rows:
            changed.extend(rows)
    return sorted(set(changed))


def _acceptance_summary(project: Project, task_id: str) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for row in project.evidence_readonly(task_id):
        for check in row.get("checks", []):
            summary.append(
                {
                    "id": check.get("check_id"),
                    "command": check.get("command"),
                    "ok": check.get("ok"),
                }
            )
    return summary


def _sheet_scenes(
    task_title: str,
    request: str,
    changed: list[str],
    checks: list[dict[str, Any]],
    duration: int,
) -> list[dict[str, Any]]:
    """Five-beat structure: hook, establish, proof, craft, button.

    Times are proportional to the declared duration and sum to it exactly.
    """
    n_checks = min(len(checks), 3)
    fractions = [
        ("hook", 0.15),
        ("establish", 0.25),
        ("proof", 0.25),
        ("craft", 0.20),
        ("button", 0.15),
    ]
    scenes: list[dict[str, Any]] = []
    cursor = 0.0
    for name, fraction in fractions:
        span = round(duration * fraction, 2)
        scene: dict[str, Any] = {
            "name": name,
            "start": round(cursor, 2),
            "duration": span,
            "kind": "text",
        }
        if name == "hook":
            scene["text"] = task_title
        elif name == "establish":
            scene["text"] = request if request else task_title
        elif name == "proof":
            scene["kind"] = "list"
            scene["items"] = [c.get("id") or "check" for c in checks[:n_checks]] or [
                "acceptance checks passed"
            ]
        elif name == "craft":
            scene["kind"] = "files"
            scene["items"] = changed[:4] or ["the delivered work"]
        elif name == "button":
            scene["kind"] = "logo"
            scene["text"] = task_title
        scenes.append(scene)
        cursor = round(cursor + span, 2)
    # Rounding drift lands on the last scene so times sum exactly.
    drift = round(duration - cursor, 2)
    if scenes and drift:
        scenes[-1]["duration"] = round(scenes[-1]["duration"] + drift, 2)
    return scenes


def build_promo(
    project: Project,
    task_id: str,
    *,
    duration: int = 12,
    vertical: bool = False,
) -> dict[str, Any]:
    """Draft the promo shot sheet and plan for a completed task.

    The task must be done with a confirmed review: the promo showcases
    verified work, and the review signature is part of the sourced proof.
    """
    task = project.get_task(task_id)
    if task.status != "done":
        raise PromoError(
            f"task is {task.status}; a promo showcases completed work — fly the task to done first"
        )
    if not task.plan_id:
        raise PromoError("task has no plan; nothing to showcase")
    plan = project.get_plan(task.plan_id)
    review = task.review
    if review is None or review.verdict != "confirmed":
        raise PromoError("task has no confirmed review; the promo cannot cite one")

    changed = _changed_files(project, task_id)
    checks = _acceptance_summary(project, task_id)
    if not task.verify_id:
        raise PromoError("task has no verification evidence")

    width, height = (1080, 1920) if vertical else (1920, 1080)
    if duration < 8 or duration > 30:
        raise PromoError("duration must be 8..30 seconds")

    scenes = _sheet_scenes(task.title, task.request, changed, checks, duration)
    total = round(sum(scene["duration"] for scene in scenes), 2)
    if abs(total - duration) > 0.01:
        raise PromoError(f"shot sheet times sum to {total}, not {duration}")

    sheet = {
        "logline": f"{task.title} — built and verified through the Aperio loop",
        "duration_s": duration,
        "fps": 30,
        "width": width,
        "height": height,
        "palette": PALETTE,
        "sakuga_shot": "craft",
        "scenes": scenes,
        "sourced_from": {
            "task_id": task.id,
            "plan_id": plan.id,
            "review": {"reviewer": review.reviewer, "verdict": review.verdict},
            "changed_files": changed,
            "acceptance_checks": checks,
        },
        "doctrine": "docs/MOTION.md",
    }

    composition = _composition_html(sheet)
    render_script = _render_script(width, height, duration)

    promo_plan = {
        "title": f"Promo video: {task.title}",
        "request": (
            f"Render the {duration}s launch promo for '{task.title}' from the approved "
            f"shot sheet in promo/shot-sheet.json (source task {task.id})."
        ),
        "builder": "promo-builder",
        "allowed_paths": ["promo/"],
        "steps": [
            _write_step("promo/shot-sheet.json", json.dumps(sheet, indent=2) + "\n"),
            _write_step("promo/composition.html", composition),
            _write_step("promo/render.sh", render_script),
        ],
        "acceptance": [
            _acceptance("sheet-times-sum", _times_sum_command(duration)),
            _acceptance("determinism-contract", NO_RANDOM_COMMAND),
            _acceptance("composition-declared", "grep -q 'name=\"hyperframes\"' promo/composition.html"),
            _acceptance("render-script-present", "test -f promo/render.sh"),
        ],
    }
    return {
        "sheet": sheet,
        "promo_plan": promo_plan,
        "note": (
            "The promo plan is a normal Aperio plan: approve it, run it, verify it. "
            "Rendering requires the HyperFrames toolchain (Node 22+); install it "
            "through `apero tool` and run promo/render.sh after the plan applies. "
            "The render command is NOT executed by Aperio."
        ),
    }


def _write_step(path: str, content: str) -> dict[str, Any]:
    """A write-step dict for the generated promo plan (kept as dicts so the
    generated plan is plain JSON the CLI can consume)."""
    return {"id": "write-" + path.replace("/", "-").replace(".", "-"), "kind": "write", "path": path, "content": content}


def _acceptance(cid: str, command: str) -> dict[str, Any]:
    return {"id": cid, "command": command}


NO_RANDOM_COMMAND = (
    "! grep -rnE 'Math\\.random|Date\\.now' promo/composition.html"
)


def _times_sum_command(duration: int) -> str:
    return (
        "python3 -c \"import json; s=json.load(open('promo/shot-sheet.json')); "
        f"total=sum(sc['duration'] for sc in s['scenes']); "
        f"assert abs(total - {duration}) < 0.011, total; "
        "assert len(s['scenes']) >= 3\""
    )


def _composition_html(sheet: dict[str, Any]) -> str:
    """A deterministic starter composition under the docs/MOTION.md contract."""
    scenes = sheet["scenes"]
    width = sheet["width"]
    height = sheet["height"]
    duration = sheet["duration_s"]
    palette = sheet["palette"]
    scene_css = []
    scene_js = []
    for index, scene in enumerate(scenes):
        start = scene["start"]
        span = scene["duration"]
        selector = f".scene-{index}"
        scene_css.append(
            f"{selector} {{ position:absolute; inset:0; display:flex; "
            "align-items:center; justify-content:center; flex-direction:column; "
            f"opacity:0; }}\n{selector} .text {{ color: {palette['ink']}; "
            "font-family: 'Inter', sans-serif; font-weight: 700; "
            f"font-size: {height // 12}px; }}\n{selector} .item {{ color: {palette['muted']}; "
            f"font-size: {height // 24}px; margin: 4px; }}"
        )
        scene_js.append(
            f"tl.fromTo('{selector}', {{opacity: 0, y: 40}}, "
            f"{{opacity: 1, y: 0, duration: 0.6, ease: 'power4.out'}}, {start});\n"
            f"tl.to('{selector}', {{opacity: 1, duration: {max(span - 0.6, 0.1)}}}, {start + 0.6});\n"
            f"tl.to('{selector}', {{opacity: 0, duration: 0.25, ease: 'power2.in'}}, {round(start + span - 0.25, 2)});"
        )
    items_html = "".join(
        f"<div class='scene scene-{i}'>"
        + (
            f"<div class='text'>{s.get('text', '')}</div>"
            if s.get("text")
            else "".join(f"<div class='item'>{item}</div>" for item in s.get("items", []))
        )
        + "</div>"
        for i, s in enumerate(scenes)
    )
    return (
        "<!doctype html>\n"
        f"<html lang=\"en\"><head><meta charset=\"utf-8\">\n"
        f"<meta name=\"hyperframes\" content=\"duration:{duration},fps:30,width:{width},height:{height}\">\n"
        "<title>Aperio promo</title>\n"
        "<style>\n"
        f"body {{ margin:0; background: {palette['bg']}; width:{width}px; height:{height}px; overflow:hidden; }}\n"
        + "\n".join(scene_css)
        + "\n</style></head><body>\n"
        + items_html
        + "\n<script src='https://cdn.jsdelivr.net/npm/gsap@3.14/dist/gsap.min.js'></script>\n"
        "<script>\n"
        "window.__timelines = window.__timelines || {};\n"
        "const tl = gsap.timeline({ paused: true, defaults: { ease: 'power4.out' } });\n"
        + "\n".join(scene_js)
        + "\nwindow.__timelines.root = tl;\n"
        "</script></body></html>\n"
    )


def _render_script(width: int, height: int, duration: int) -> str:
    return (
        "#!/bin/sh\n"
        "# Render the promo with HyperFrames (installed via `apero tool`).\n"
        "# Aperio does not run this script; the owner or a rendered plan step does.\n"
        "set -e\n"
        "cd \"$(dirname \"$0\")\"\n"
        f"npx hyperframes render composition.html --width {width} --height {height} "
        f"--duration {duration} --fps 30 --output promo.mp4\n"
        "echo \"rendered promo.mp4\"\n"
    )
