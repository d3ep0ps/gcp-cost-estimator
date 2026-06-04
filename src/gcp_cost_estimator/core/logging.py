# SPDX-License-Identifier: Apache-2.0

import logging
import os
import sys
from pathlib import Path


def configure_logging() -> None:
    """Configures the 'gcp_cost_estimator' logger.

    Reads configuration from environment variables:
    - GCP_BILLING_LOG_LEVEL: default to 'INFO'
    - GCP_BILLING_LOG_FILE: path to log file. If set to 'none' or empty, file logging is disabled.
      If unset, defaults to '~/.gcp-cost-estimator/mcp.log'.
    """
    level_str = os.environ.get("GCP_BILLING_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)

    logger = logging.getLogger("gcp_cost_estimator")
    logger.setLevel(level)
    logger.propagate = False

    # Clear existing handlers to avoid duplicates on re-configuration
    logger.handlers.clear()

    # Formatter for structured logs
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Stderr stream handler (safe for MCP stdio transport since stdout is reserved)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    # Determine file handler path
    log_file_env = os.environ.get("GCP_BILLING_LOG_FILE")
    if log_file_env and log_file_env.lower() == "none":
        return

    if log_file_env:
        log_file_path = Path(log_file_env)
    else:
        home_dir = Path.home() / ".gcp-cost-estimator"
        log_file_path = home_dir / "mcp.log"

    try:
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to setup file logging at {log_file_path}: {e}\n")
