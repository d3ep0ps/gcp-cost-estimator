# SPDX-License-Identifier: Apache-2.0

import re
from typing import Any


def parse_k8s_quantity(val: Any, is_cpu: bool = False) -> str:
    """Parse k8s quantity string to a standardized string representation.

    CPU: "1000m" -> "1", "1.5" -> "1.5"
    Memory: "512Mi" -> "0.5", "1Gi" -> "1.0", "1024M" -> "1.024"
    """
    if val is None:
        return ""
    val_str = str(val).strip()
    if not val_str:
        return ""

    try:
        float(val_str)
        if not is_cpu:
            # If it's memory and is a whole float (like 2 or 2.0), return "2.0"
            f_val = float(val_str)
            if f_val.is_integer():
                return f"{int(f_val)}.0"
            return f"{f_val:.4f}".rstrip("0").rstrip(".")
        return val_str
    except ValueError:
        pass

    if is_cpu:
        if val_str.endswith("m"):
            try:
                milli = float(val_str[:-1])
                res = milli / 1000.0
                return f"{res:g}"
            except ValueError:
                return val_str
        return val_str
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([a-zA-Z]+)$", val_str)
    if not m:
        return val_str
    num_str, suffix = m.group(1), m.group(2)
    try:
        num = float(num_str)
    except ValueError:
        return val_str

    suffix_lower = suffix.lower()
    if suffix_lower == "ki":
        bytes_val = num * 1024
    elif suffix_lower == "mi":
        bytes_val = num * 1024 * 1024
    elif suffix_lower == "gi":
        bytes_val = num * 1024 * 1024 * 1024
    elif suffix_lower == "ti":
        bytes_val = num * 1024 * 1024 * 1024 * 1024
    elif suffix_lower == "k":
        bytes_val = num * 1000
    elif suffix_lower == "m":
        bytes_val = num * 1000 * 1000
    elif suffix_lower == "g":
        bytes_val = num * 1000 * 1000 * 1000
    elif suffix_lower == "t":
        bytes_val = num * 1000 * 1000 * 1000 * 1000
    else:
        return val_str

    gib = bytes_val / (1024 * 1024 * 1024)
    if gib.is_integer():
        return f"{int(gib)}.0"
    return f"{gib:.4f}".rstrip("0").rstrip(".")
