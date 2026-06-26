#!/usr/bin/env python3
"""Compile judgment verdict statistics into a markdown report."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JUDGMENTS_DIR = ROOT / "judgments"
OUTPUT_PATH = ROOT / "judgment_statistics.md"

VERDICTS = ("pass", "fail", "engine-missing")

ISSUE_CATEGORIES: list[tuple[str, re.Pattern[str]]] = [
    (
        "Keywords / timing labels",
        re.compile(
            r"\bkeyword|keywords\b|fanfare\b.*timing|timing\b.*not.*keyword|"
            r"represented by the .+ ability timing|not printed keywords",
            re.I,
        ),
    ),
    (
        "Missing or unimplemented effects",
        re.compile(
            r"\b(missing|unimplemented|noop|completely missing|is missing its|"
            r"effect is missing|ability is missing|not encoded|left as noop)\b",
            re.I,
        ),
    ),
    (
        "Wrong ability timing or structure",
        re.compile(
            r"\b(incorrectly encoded as|wrong timing|should be a (passive|fanfare|activated|spell)|"
            r"encoded as an activated|encoded as a fanfare|not a fanfare|"
            r"ability wrapper|timing is wrong)\b",
            re.I,
        ),
    ),
    (
        "Targets and selection",
        re.compile(
            r"\btarget|select(?:ion|ed)?\b|filter\b|scope\b|selfFollower|enemyFollower|"
            r"wrong target|targets are",
            re.I,
        ),
    ),
    (
        "Damage, amounts, and counting",
        re.compile(
            r"\b(damage|amount|count|divisor|multiplier|rounded|half|X equals|"
            r"dynamic amount|field count|cemetery count)\b",
            re.I,
        ),
    ),
    (
        "Conditions and restrictions",
        re.compile(
            r"\bcondition|restriction|only if|can't be played|threshold|"
            r"at least \d+|unless|when playing\b",
            re.I,
        ),
    ),
    (
        "Costs (play, activate, optional)",
        re.compile(
            r"\b(cost|optionalCost|additional cost|play-cost|activation cost|"
            r"bury|banish|discard.*cost|Lesson|engage)\b",
            re.I,
        ),
    ),
    (
        "Search, deck, and zone effects",
        re.compile(
            r"\b(search|deck|tutor|shuffle|hand|cemetery|EX area|graveyard|mill|draw)\b",
            re.I,
        ),
    ),
    (
        "Choose / branching effects",
        re.compile(
            r"\bchoose|chooseMultiple|option|branch|choose one\b",
            re.I,
        ),
    ),
    (
        "Evolve and linkage",
        re.compile(
            r"\b(evolve|evolvesTo|evolvesFrom|onEvolve|onSuperEvolve|super-evolve|"
            r"evolved|specialType)\b",
            re.I,
        ),
    ),
    (
        "Engine capability gaps",
        re.compile(
            r"\b(implement support|engine (?:does not|reference does not)|"
            r"if not (?:already )?available|requires engine support|"
            r"not available using|engine-missing)\b",
            re.I,
        ),
    ),
]


def load_judgments(directory: Path) -> tuple[dict[str, dict], list[str]]:
    cards: dict[str, dict] = {}
    parse_errors: list[str] = []
    for path in sorted(directory.glob("batch-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            parse_errors.append(f"{path.name}: {exc}")
            continue
        if not isinstance(data, dict):
            parse_errors.append(f"{path.name}: expected object")
            continue
        for card_name, entry in data.items():
            if card_name in cards:
                cards[card_name]["sources"].append(path.name)
            else:
                cards[card_name] = {
                    "verdict": entry.get("verdict", "unknown"),
                    "issues": entry.get("issues") or [],
                    "sources": [path.name],
                }
    return cards, parse_errors


def categorize_issue(text: str) -> str:
    for label, pattern in ISSUE_CATEGORIES:
        if pattern.search(text):
            return label
    return "Other"


def pct(n: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{100 * n / total:.1f}%"


def build_report(cards: dict[str, dict], parse_errors: list[str]) -> str:
    verdict_counts = Counter()
    issue_counts_by_verdict: dict[str, Counter[str]] = {
        v: Counter() for v in VERDICTS if v != "pass"
    }
    issue_examples: dict[str, dict[str, list[str]]] = {
        v: defaultdict(list) for v in VERDICTS if v != "pass"
    }

    for card in cards.values():
        verdict = card["verdict"]
        verdict_counts[verdict] += 1
        if verdict not in issue_counts_by_verdict:
            continue
        for issue in card["issues"]:
            category = categorize_issue(issue)
            issue_counts_by_verdict[verdict][category] += 1
            examples = issue_examples[verdict][category]
            if len(examples) < 3:
                examples.append(issue)

    total_cards = sum(verdict_counts.values())
    judged_cards = verdict_counts["pass"] + verdict_counts["fail"] + verdict_counts["engine-missing"]
    total_issues = sum(
        sum(counter.values()) for counter in issue_counts_by_verdict.values()
    )

    lines = [
        "# Judgment Statistics",
        "",
        f"Generated from `{JUDGMENTS_DIR.name}/batch-*.json`.",
        "",
        "## Overview",
        "",
        f"| Metric | Count |",
        f"|--------|------:|",
        f"| Judgment batch files | {len(list(JUDGMENTS_DIR.glob('batch-*.json')))} |",
        f"| Unique cards judged | {total_cards} |",
        f"| Total issues recorded | {total_issues} |",
        "",
        "## Verdict counts",
        "",
        "| Verdict | Cards | Share of judged |",
        "|---------|------:|----------------:|",
    ]

    for verdict in VERDICTS:
        count = verdict_counts[verdict]
        lines.append(f"| `{verdict}` | {count} | {pct(count, judged_cards)} |")
    if verdict_counts["unknown"]:
        lines.append(f"| `unknown` | {verdict_counts['unknown']} | {pct(verdict_counts['unknown'], total_cards)} |")

    lines.extend(
        [
            "",
            f"**Pass rate:** {pct(verdict_counts['pass'], judged_cards)}",
            f"**Fail rate:** {pct(verdict_counts['fail'], judged_cards)}",
            f"**Engine-missing rate:** {pct(verdict_counts['engine-missing'], judged_cards)}",
            "",
        ]
    )

    for verdict in ("fail", "engine-missing"):
        lines.extend(
            [
                f"## Issue categories — `{verdict}`",
                "",
                f"Cards with `{verdict}`: **{verdict_counts[verdict]}**. "
                f"Issues grouped by primary category ({sum(issue_counts_by_verdict[verdict].values())} issue statements).",
                "",
                "| Category | Issues | Share |",
                "|----------|-------:|------:|",
            ]
        )
        counter = issue_counts_by_verdict[verdict]
        verdict_issue_total = sum(counter.values()) or 1
        for category, count in counter.most_common():
            lines.append(f"| {category} | {count} | {pct(count, verdict_issue_total)} |")
        lines.append("")

        lines.append("### Example issues by category")
        lines.append("")
        for category, count in counter.most_common():
            if count == 0:
                continue
            lines.append(f"#### {category}")
            lines.append("")
            for example in issue_examples[verdict][category]:
                lines.append(f"- {example}")
            lines.append("")

    if parse_errors:
        lines.extend(["## Parse errors", ""])
        for error in parse_errors:
            lines.append(f"- {error}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    if not JUDGMENTS_DIR.is_dir():
        raise FileNotFoundError(f"Missing judgments directory: {JUDGMENTS_DIR}")
    cards, parse_errors = load_judgments(JUDGMENTS_DIR)
    report = build_report(cards, parse_errors)
    OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
