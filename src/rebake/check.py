from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from rebake.config import RebakeConfig, TemplateEntry
from rebake.utils.git import resolve_template_commit


class CheckResult(Enum):
    UP_TO_DATE = "up-to-date"
    OUTDATED = "outdated"


@dataclass
class EntryCheck:
    entry: TemplateEntry
    head_commit: str
    result: CheckResult


def check_entries(project_dir: Path = Path("."), names: Sequence[str] | None = None) -> list[EntryCheck]:
    """Check the registered template links against their remote HEADs.

    By default every link is checked. Pass ``names`` to scope the report to the
    links with those ``name``s (see ``RebakeConfig.select``).
    """
    config = RebakeConfig.load(project_dir)
    checks: list[EntryCheck] = []
    for entry in config.select(names):
        head_commit = resolve_template_commit(entry.template, checkout=entry.checkout)
        result = CheckResult.UP_TO_DATE if entry.commit == head_commit else CheckResult.OUTDATED
        checks.append(EntryCheck(entry=entry, head_commit=head_commit, result=result))
    return checks


def is_up_to_date(project_dir: Path = Path(".")) -> CheckResult:
    """Overall status: UP_TO_DATE only when every template link is up-to-date."""
    checks = check_entries(project_dir)
    if all(check.result == CheckResult.UP_TO_DATE for check in checks):
        return CheckResult.UP_TO_DATE
    return CheckResult.OUTDATED
