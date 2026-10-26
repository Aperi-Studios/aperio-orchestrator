"""Persistent, deterministic discovery interview for Aperio.

The chat host asks the questions; this module owns the record. It stores
numbered answers, evidence references, research requests, and readiness in the
project state. It does not call a model and does not invent an answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from .model import ModelError, utc_now
from .store import Project

SCHEMA_VERSION = 1
DISCOVERY_FILE = "discovery.json"


class DiscoveryError(ModelError):
    """A discovery question, answer, or state is invalid."""


@dataclass(frozen=True)
class Choice:
    value: str
    label: str


@dataclass(frozen=True)
class Question:
    id: str
    domain: str
    prompt: str
    why: str
    choices: tuple[Choice, ...] = ()
    multi: bool = False
    allow_text: bool = True
    requires: tuple[str, ...] = ()


def _c(value: str, label: str) -> Choice:
    return Choice(value, label)


QUESTIONS: tuple[Question, ...] = (
    Question(
        "idea",
        "intent",
        "In one or two sentences, what do you want to make?",
        "The idea decides every later question; do not ask for a business metric before the thing exists.",
    ),
    Question(
        "users",
        "users",
        "Who is the primary person this is for, and what one action should they be able to take?",
        "The audience and the primary action decide the first release.",
    ),
    Question(
        "success",
        "measurement",
        "How will you know it worked?",
        "A measurable target is stronger than “looks good”.",
        (
            _c("orders", "More orders, leads, sales, or bookings"),
            _c("time", "Less manual work or fewer errors"),
            _c("launch", "A launch by a specific date"),
            _c("search", "Better search visibility"),
            _c("quality", "Better speed, accessibility, or usability"),
            _c("not_sure", "Not sure — research and recommend"),
        ),
        allow_text=True,
    ),
    Question(
        "must_haves",
        "scope",
        "What are the three must-haves for the first release?",
        "A small first release is testable; a large list is not.",
    ),
    Question(
        "non_goals",
        "scope",
        "What is explicitly not included in the first release?",
        "Non-goals protect the plan from quiet scope growth.",
    ),
    Question(
        "constraints",
        "constraints",
        "What is fixed? Choose all that apply.",
        "Fixed constraints change the safe options.",
        (
            _c("deadline", "Deadline"),
            _c("budget", "Budget"),
            _c("brand", "Brand or design"),
            _c("stack", "Existing technology or stack"),
            _c("hosting", "Hosting or domain"),
            _c("legal", "Legal, privacy, or compliance"),
            _c("language", "Languages or localization"),
            _c("accessibility", "Accessibility target"),
            _c("none", "Nothing is fixed"),
            _c("not_sure", "Not sure — research and recommend"),
        ),
        multi=True,
    ),
    Question(
        "ownership",
        "governance",
        "Who owns the domain, hosting, repository, content, analytics, and final approval?",
        "Ownership prevents work being trapped in someone else's account.",
        (
            _c("owner", "I own everything"),
            _c("team", "My team owns it"),
            _c("client", "A client owns it"),
            _c("not_sure", "Not sure — research and recommend"),
        ),
    ),
    Question(
        "evidence",
        "evidence",
        "What evidence can you show? Choose all that apply.",
        "Existing evidence prevents the agent from guessing at the current state.",
        (
            _c("url", "An existing URL"),
            _c("repo", "A repository or folder"),
            _c("analytics", "Analytics or Search Console"),
            _c("brand", "Brand assets or examples"),
            _c("screenshots", "Screenshots, logs, or error messages"),
            _c("none", "Nothing yet"),
            _c("not_sure", "Not sure — research and recommend"),
        ),
        multi=True,
    ),
    Question(
        "labels",
        "scope",
        "Which labels apply? Choose all that apply.",
        "Labels load the right question modules; they are not a project type.",
        (
            _c("new", "New build"),
            _c("change", "Change or extend"),
            _c("redesign", "Redesign"),
            _c("repair", "Repair"),
            _c("audit", "Audit"),
            _c("migrate", "Migration or replacement"),
            _c("seo", "SEO or growth"),
            _c("quality", "Performance or accessibility"),
            _c("commerce", "Commerce, payments, or bookings"),
            _c("cms", "CMS or editorial workflow"),
        ),
        multi=True,
    ),
    Question(
        "commerce_flow",
        "commerce",
        "How should a customer complete an order?",
        "This decides the checkout, order storage, and support path.",
        (
            _c("request", "Browse and send an order request — no cart"),
            _c("cart_cod", "Cart + guest checkout with cash on delivery"),
            _c("cart_online", "Cart + online payment"),
            _c("not_sure", "Not sure — research and recommend"),
        ),
        requires=("commerce",),
    ),
    Question(
        "commerce_delivery",
        "commerce",
        "How should delivery charges work?",
        "Delivery pricing decides the checkout fields and the order total.",
        (
            _c("fixed", "One fixed charge"),
            _c("zone", "Different charges by zone"),
            _c("free", "Free delivery"),
            _c("not_sure", "Not sure — research and recommend"),
        ),
        requires=("commerce",),
    ),
    Question(
        "commerce_returns",
        "commerce",
        "What should happen when an order is refused or returned?",
        "COD refusal is a real cost; the policy cannot stay undefined.",
        (
            _c("customer", "Customer pays the return cost"),
            _c("business", "Business absorbs the cost"),
            _c("case", "Case by case"),
            _c("not_sure", "Not sure — research and recommend"),
        ),
        requires=("commerce",),
    ),
    Question(
        "cms_roles",
        "cms",
        "Who should be able to edit, approve, and publish content?",
        "Roles and publishing rights decide the CMS workflow.",
        (
            _c("owner", "Only the owner"),
            _c("team", "Owner and team roles"),
            _c("approval", "Editor plus approver"),
            _c("not_sure", "Not sure — research and recommend"),
        ),
        requires=("cms",),
    ),
    Question(
        "cms_model",
        "cms",
        "What content types need to be editable?",
        "The content model decides the CMS schema and the edit screen.",
        requires=("cms",),
    ),
    Question(
        "seo_baseline",
        "seo",
        "What search or analytics baseline do you have?",
        "Without a baseline, SEO claims cannot be measured.",
        (
            _c("gsc", "Google Search Console"),
            _c("analytics", "Analytics only"),
            _c("both", "Both Search Console and analytics"),
            _c("none", "Neither yet"),
            _c("not_sure", "Not sure — research and recommend"),
        ),
        requires=("seo",),
    ),
    Question(
        "seo_urls",
        "seo",
        "Will any URLs change, or must any existing URLs be preserved?",
        "A URL map is required before a redesign or migration.",
        (
            _c("none", "No URLs change"),
            _c("map", "Yes — a redirect map is needed"),
            _c("not_sure", "Not sure — research and recommend"),
        ),
        allow_text=True,
        requires=("seo",),
    ),
    Question(
        "migration_urls",
        "migration",
        "Will the domain, platform, or URL structure change?",
        "The migration path and redirect plan depend on this answer.",
        (
            _c("none", "No — same platform and URLs"),
            _c("map", "Yes — a URL/data map is needed"),
            _c("not_sure", "Not sure — research and recommend"),
        ),
        requires=("migrate",),
    ),
    Question(
        "migration_rollback",
        "migration",
        "How should rollback work if the migration fails?",
        "A migration without a rollback path is not safe to run.",
        (
            _c("old", "Restore the old site"),
            _c("both", "Keep both available"),
            _c("not_sure", "Not sure — research and recommend"),
        ),
        requires=("migrate",),
    ),
    Question(
        "quality_target",
        "quality",
        "Which quality target matters first?",
        "Accessibility and performance need a target before testing.",
        (
            _c("accessibility", "Accessibility — WCAG 2.2 AA"),
            _c("performance", "Performance — Core Web Vitals budget"),
            _c("both", "Both"),
            _c("not_sure", "Not sure — research and recommend"),
        ),
        requires=("quality",),
    ),
    Question(
        "name",
        "delivery",
        "What should the project be called?",
        "A working name is enough; it does not need to be the final brand.",
    ),
)

QUESTION_BY_ID = {question.id: question for question in QUESTIONS}

SUMMARY_LABELS = {
    "idea": "Idea",
    "users": "Primary user and action",
    "success": "Success measure",
    "must_haves": "Must-haves",
    "non_goals": "Not included",
    "constraints": "Fixed constraints",
    "ownership": "Ownership",
    "evidence": "Evidence",
    "labels": "Labels",
    "commerce_flow": "Commerce order path",
    "commerce_delivery": "Delivery charges",
    "commerce_returns": "Refused or returned orders",
    "cms_roles": "CMS roles",
    "cms_model": "CMS content types",
    "seo_baseline": "SEO baseline",
    "seo_urls": "SEO URLs",
    "migration_urls": "Migration URL map",
    "migration_rollback": "Migration rollback",
    "quality_target": "Quality target",
    "name": "Project name",
}


def _new_state() -> dict[str, Any]:
    now = utc_now()
    return {
        "schema": SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
        "answers": {},
        "waivers": {},
    }


def _state(project: Project) -> dict[str, Any]:
    data = project.discovery()
    if data is None:
        data = _new_state()
        project.save_discovery(data)
        return data
    return _read_state(data)


def _read_state(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        raise DiscoveryError("discovery state is missing")
    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        raise DiscoveryError("discovery state is malformed")
    if not isinstance(data.get("waivers"), dict):
        data["waivers"] = {}
    return data


def _answer_complete(answer: dict[str, Any] | None) -> bool:
    if not isinstance(answer, dict) or answer.get("status") != "answered":
        return False
    values = answer.get("values")
    text = answer.get("text")
    return bool(values) or bool(str(text or "").strip())


def _labels(data: dict[str, Any]) -> set[str]:
    answer = data.get("answers", {}).get("labels", {})
    return set(answer.get("values", []))


def _applicable(data: dict[str, Any]) -> list[Question]:
    labels = _labels(data)
    return [
        question for question in QUESTIONS if all(label in labels for label in question.requires)
    ]


def next_question(project: Project) -> Question | None:
    data = _state(project)
    waivers = data.get("waivers", {})
    for question in _applicable(data):
        if question.id in waivers:
            continue
        answer = data["answers"].get(question.id)
        if answer is None or answer.get("status") == "research" or not _answer_complete(answer):
            return question
    return None


def question_index(project: Project, question_id: str) -> int:
    data = _state(project)
    for index, question in enumerate(_applicable(data), 1):
        if question.id == question_id:
            return index
    raise DiscoveryError(f"unknown question: {question_id}")


def _choice_by_number(question: Question, number: int) -> Choice:
    if number < 1 or number > len(question.choices):
        raise DiscoveryError(f"{question.id}: choice must be 1..{len(question.choices)}")
    return question.choices[number - 1]


def parse_choices(question: Question, raw: str) -> list[str]:
    if not raw.strip():
        return []
    values: list[str] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if token.isdecimal():
            if len(token) > 4:
                raise DiscoveryError(f"{question.id}: choice number is too large")
            try:
                number = int(token)
            except ValueError as exc:
                raise DiscoveryError(f"{question.id}: unknown choice: {token}") from exc
            values.append(_choice_by_number(question, number).value)
        elif token in {choice.value for choice in question.choices}:
            values.append(token)
        else:
            raise DiscoveryError(f"{question.id}: unknown choice: {token}")
    if len(values) != len(set(values)):
        raise DiscoveryError(f"{question.id}: choice repeated")
    if not question.multi and len(values) > 1:
        raise DiscoveryError(f"{question.id}: choose only one option")
    return values


def answer_question(
    project: Project,
    question_id: str,
    choices: list[str] | None = None,
    text: str = "",
    evidence: str = "",
) -> dict[str, Any]:
    question = QUESTION_BY_ID.get(question_id)
    if question is None:
        raise DiscoveryError(f"unknown question: {question_id}")
    values = choices or []
    text = text.strip()
    evidence = evidence.strip()
    if len(values) != len(set(values)):
        raise DiscoveryError(f"{question.id}: choice repeated")
    valid_values = {choice.value for choice in question.choices}
    if values and not question.choices:
        raise DiscoveryError(f"{question.id}: this question takes a text answer")
    if values and any(value not in valid_values for value in values):
        raise DiscoveryError(f"{question.id}: unknown choice")
    if not question.multi and len(values) > 1:
        raise DiscoveryError(f"{question.id}: choose only one option")
    if not values and not text:
        raise DiscoveryError(f"{question.id}: answer text is required")
    if "other" in values and not text:
        raise DiscoveryError(f"{question.id}: text is required for other")
    if not question.allow_text and not values:
        raise DiscoveryError(f"{question.id}: choose an option")

    data = _state(project)
    labels = _labels(data)
    if question.requires and not all(label in labels for label in question.requires):
        raise DiscoveryError(f"{question.id}: answer the labels question first")

    status = "research" if "not_sure" in values else "answered"
    data["answers"][question.id] = {
        "values": values,
        "text": text,
        "evidence": evidence,
        "status": status,
        "recorded_at": utc_now(),
    }
    data.setdefault("waivers", {}).pop(question.id, None)
    data["updated_at"] = utc_now()
    project.save_discovery(data)
    return data["answers"][question.id]


WAIVER_CONFIRM = "I accept this risk"


def waive_question(
    project: Project,
    question_id: str,
    by: str,
    risk: str,
    confirm: str,
    review_at: str,
) -> dict[str, Any]:
    question = QUESTION_BY_ID.get(question_id)
    if question is None:
        raise DiscoveryError(f"unknown question: {question_id}")
    if question_id == "labels":
        raise DiscoveryError("labels controls conditional questions; answer it instead of waiving")
    if confirm != WAIVER_CONFIRM:
        raise DiscoveryError(f"confirmation must be exactly: {WAIVER_CONFIRM}")
    if not by.strip():
        raise DiscoveryError("waiver needs an owner name")
    if not risk.strip():
        raise DiscoveryError("waiver needs a stated risk")
    if not review_at.strip():
        raise DiscoveryError("waiver needs a review date")
    try:
        review_date = date.fromisoformat(review_at.strip())
    except ValueError as exc:
        raise DiscoveryError("review date must be YYYY-MM-DD") from exc
    if review_date < date.today():
        raise DiscoveryError("review date must not be in the past")
    data = _state(project)
    if question.requires and not all(label in _labels(data) for label in question.requires):
        raise DiscoveryError(f"{question_id}: answer the labels question first")
    existing = data.get("answers", {}).get(question_id, {})
    if existing.get("status") == "answered":
        raise DiscoveryError(f"{question_id}: already answered; a waiver is not needed")
    waiver = {
        "by": by.strip(),
        "risk": risk.strip(),
        "review_at": review_at.strip(),
        "accepted_at": utc_now(),
        "confirm": confirm,
        "status": "waived",
    }
    data.setdefault("waivers", {})[question_id] = waiver
    data["updated_at"] = utc_now()
    project.save_discovery(data)
    return waiver


def status(project: Project) -> dict[str, Any]:
    data = project.discovery()
    if data is None:
        applicable = _applicable({})
        return {
            "total": len(applicable),
            "answered": 0,
            "research": 0,
            "missing": [question.id for question in applicable],
            "waived": [],
            "waived_research": [],
            "ready": False,
            "next": applicable[0].id,
            "answers": {},
            "waivers": {},
        }
    data = _read_state(data)
    answers = data.get("answers", {})
    waivers = data.get("waivers", {})
    applicable = _applicable(data)
    missing = [
        question.id
        for question in applicable
        if question.id not in waivers
        and (question.id not in answers or not _answer_complete(answers.get(question.id)))
        and answers.get(question.id, {}).get("status") != "research"
    ]
    research = [
        question.id
        for question in applicable
        if question.id not in waivers
        and answers.get(question.id, {}).get("status") == "research"
    ]
    answered = [
        question.id
        for question in applicable
        if _answer_complete(answers.get(question.id))
    ]
    waived = [question.id for question in applicable if question.id in waivers]
    waived_research = [
        question.id
        for question in applicable
        if question.id in waivers
        and answers.get(question.id, {}).get("status") == "research"
    ]
    ready = not missing and not research
    return {
        "total": len(applicable),
        "answered": len(answered),
        "research": len(research),
        "missing": missing,
        "waived": waived,
        "waived_research": waived_research,
        "ready": ready,
        "next": missing[0] if missing else (research[0] if research else None),
        "answers": answers,
        "waivers": waivers,
    }


def summary(project: Project) -> str:
    data = _read_state(project.discovery()) if project.discovery() is not None else {}
    answers = data.get("answers", {})
    waivers = data.get("waivers", {})
    lines = ["# Discovery summary", ""]
    for question in _applicable(data):
        waiver = waivers.get(question.id)
        if waiver:
            suffix = " (research was requested)" if answers.get(question.id, {}).get("status") == "research" else ""
            lines.append(
                f"- **{SUMMARY_LABELS.get(question.id, question.domain)}:** "
                f"WAIVED by {waiver.get('by', 'unknown')} — {waiver.get('risk', 'no risk stated')}"
                f" (review by {waiver.get('review_at', 'not set')}){suffix}"
            )
            continue
        answer = answers.get(question.id)
        if not _answer_complete(answer):
            lines.append(f"- **{SUMMARY_LABELS.get(question.id, question.domain)}:** missing")
            continue
        labels = [
            choice.label for choice in question.choices if choice.value in answer.get("values", [])
        ]
        value = ", ".join(labels)
        if answer.get("text"):
            value = f"{value} — {answer['text']}" if value else answer["text"]
        if answer.get("status") == "research":
            value = f"{value} (research requested)"
        if answer.get("evidence"):
            value = f"{value} [evidence: {answer['evidence']}]"
        lines.append(f"- **{SUMMARY_LABELS.get(question.id, question.domain)}:** {value}")
    return "\n".join(lines)


def format_question(project: Project, question: Question) -> str:
    data = _state(project)
    index = question_index(project, question.id)
    lines = [f"Discovery {index} of {len(_applicable(data))} · {question.domain}", "", question.prompt, ""]
    if question.choices:
        for number, choice in enumerate(question.choices, 1):
            lines.append(f"{number}. {choice.label}")
        if question.multi:
            lines.extend(["", "Choose all that apply."])
        if question.allow_text:
            lines.extend(["", "Or type your own answer."])
    else:
        lines.append("Type your answer.")
    lines.extend(["", f"Why: {question.why}"])
    return "\n".join(lines)


def format_status(project: Project) -> str:
    result = status(project)
    if result["ready"]:
        if result["waived"]:
            return (
                f"Discovery: ready ({result['answered']} answered, "
                f"{len(result['waived'])} waived). Ready to plan.\n"
                "Waived: " + ", ".join(result["waived"])
            )
        return f"Discovery: complete ({result['total']} of {result['total']} answered). Ready to plan."
    parts = [
        f"Discovery: {result['answered']}/{result['total']} answered",
        f"{result['research']} need research",
        f"{len(result['missing'])} missing",
    ]
    if result["waived"]:
        parts.append(f"{len(result['waived'])} waived")
    lines = [" · ".join(parts), "Ready: no"]
    if result["waived"]:
        lines.append("Waived: " + ", ".join(result["waived"]))
    if result["next"]:
        question = QUESTION_BY_ID[result["next"]]
        lines.append(f"Next: {question.id} — {question.prompt}")
    if result["missing"]:
        lines.append("Missing: " + ", ".join(result["missing"]))
    return "\n".join(lines)


def format_next(project: Project) -> str:
    question = next_question(project)
    if question is None:
        return format_status(project)
    return format_question(project, question)


def as_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True)
