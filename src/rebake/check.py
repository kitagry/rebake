from __future__ import annotations

from enum import Enum
from pathlib import Path

from rebake.config import CruftConfig
from rebake.utils.git import get_template_head_commit


class CheckResult(Enum):
    UP_TO_DATE = "up-to-date"
    OUTDATED = "outdated"


def is_up_to_date(project_dir: Path = Path(".")) -> CheckResult:
    """Check whether the project is up-to-date with its template."""
    config = CruftConfig.load(project_dir)
    head_commit = get_template_head_commit(config.template, checkout=config.checkout)
    if config.commit == head_commit:
        return CheckResult.UP_TO_DATE
    return CheckResult.OUTDATED
