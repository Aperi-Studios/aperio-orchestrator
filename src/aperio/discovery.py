"""Persistent, deterministic discovery interview for Aperio.

The chat host asks the questions; this module owns the record. It stores
numbered answers, evidence references, research requests, and readiness in the
project state. It does not call a model and does not invent an answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
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
        ),
        multi=True,
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
    "name": "Project name",
}


def _new_state() -> dict[str, Any]:
    now = utc_now()
    return {
        "schema": SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
        "answers": {},
    }


def _state(project: Project) -> dict[str, Any]:
    data = project.discovery()
    if data is None:
        data = _new_state()
        project.save_discovery(data)
        return data
    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        raise DiscoveryError("discovery state is malformed")
    return data


def next_question(project: Project) -> Question | None:
    data = _state(project)
    for question in QUESTIONS:
        answer = data["answers"].get(question.id)
        if answer is None or answer.get("status") == "research":
            return question
    return None


def question_index(project: Project, question_id: str) -> int:
    for index, question in enumerate(QUESTIONS, 1):
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
        if token.isdigit():
            values.append(_choice_by_number(question, int(token)).value)
        elif token in {choice.value for choice in question.choices}:
            values.append(token)
        else:
            raise DiscoveryError(f"{question.id}: unknown choice: {token}")
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

    status = "research" if "not_sure" in values else "answered"
    data = _state(project)
    data["answers"][question.id] = {
        "values": values,
        "text": text,
        "evidence": evidence,
        "status": status,
        "recorded_at": utc_now(),
    }
    data["updated_at"] = utc_now()
    project.save_discovery(data)
    return data["answers"][question.id]


def status(project: Project) -> dict[str, Any]:
    data = project.discovery()
    if data is None:
        return {
            "total": len(QUESTIONS),
            "answered": 0,
            "research": 0,
            "missing": [question.id for question in QUESTIONS],
            "ready": False,
            "next": QUESTIONS[0].id,
            "answers": {},
        }
    answers = data.get("answers", {})
    missing = [question.id for question in QUESTIONS if question.id not in answers]
    research = [key for key, answer in answers.items() if answer.get("status") == "research"]
    answered = [key for key, answer in answers.items() if answer.get("status") == "answered"]
    ready = not missing and not research
    return {
        "total": len(QUESTIONS),
        "answered": len(answered),
        "research": len(research),
        "missing": missing,
        "ready": ready,
        "next": missing[0] if missing else (research[0] if research else None),
        "answers": answers,
    }


def summary(project: Project) -> str:
    data = project.discovery() or {}
    answers = data.get("answers", {})
    lines = ["# Discovery summary", ""]
    for question in QUESTIONS:
        answer = answers.get(question.id)
        if not answer:
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
    index = question_index(project, question.id)
    lines = [f"Discovery {index} of {len(QUESTIONS)} · {question.domain}", "", question.prompt, ""]
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
        return f"Discovery: complete ({result['total']} of {result['total']} answered). Ready to plan."
    parts = [
        f"Discovery: {result['answered']}/{result['total']} answered",
        f"{result['research']} need research",
        f"{len(result['missing'])} missing",
    ]
    lines = [" · ".join(parts), "Ready: no"]
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
