from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict, cast

# Hook events fired around `rebake update`. Defined via the functional TypedDict
# form because the keys contain a hyphen, which is not a valid Python identifier
# in the class-based form. `total=False` lets a recipe declare only one of the
# two events without satisfying the other.
HookSpec = TypedDict(
    "HookSpec",
    {
        "pre-update": list[str],
        "post-update": list[str],
    },
    total=False,
)


@dataclass
class Recipe:
    """Template-side rebake recipe.

    Holds default hooks the template author wants applied to every generated
    project. Loaded from rebake-recipe.yaml at the template root and merged
    into the generated project's rebake.yaml.hooks via a 3-way merge on update.
    """

    hooks: HookSpec = field(default_factory=lambda: cast(HookSpec, {}))
