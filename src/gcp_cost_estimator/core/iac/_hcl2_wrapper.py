# SPDX-License-Identifier: Apache-2.0

"""Typed shim around the untyped python-hcl2 library.

hcl2.load() returns dict[str, list[dict[str, Any]]] where keys are Terraform
block types ("resource", "variable", "locals", etc.) and values are lists of
block bodies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hcl2  # type: ignore[import-untyped]

HclDocument = dict[str, list[dict[str, Any]]]


def load_hcl(path: Path) -> HclDocument:
    """Load a single .tf file and return its parsed HCL document."""
    with path.open(encoding="utf-8") as fh:
        result: HclDocument = hcl2.load(fh)
    return result
