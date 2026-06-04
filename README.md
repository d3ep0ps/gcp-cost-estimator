# GCP Billing Model Context Protocol (MCP) Server

[![FastMCP](https://img.shields.io/badge/MCP-FastMCP-blue.svg)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/Python-3.14%2B-blue.svg)](https://www.python.org/)
[![Package Manager](https://img.shields.io/badge/uv-supported-green.svg)](https://github.com/astral-sh/uv)
[![Code Style](https://img.shields.io/badge/code%20style-ruff-black.svg)](https://github.com/astral-sh/ruff)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](#development--contributing)

A deterministic Model Context Protocol (MCP) server that exposes **Google Cloud Platform (GCP) cost-estimation capabilities** (IaC parsing, SKU pricing, cost calculation, comparison, and reporting) directly to MCP-enabled hosts (e.g., Claude Code, Gemini CLI, Claude Desktop, Cursor).

This server does not contain an internal LLM or orchestrator agent. Instead, it publishes **tools**, **resources**, and **prompts** that feed context and capabilities to the connecting host LLM. The host provides the natural language intelligence, while this server executes deterministic calculations.

---

## 📖 Table of Contents
1. [Core Principles](#-core-principles)
2. [Supported Services](#-supported-services)
3. [Architecture Overview](#-architecture-overview)
4. [Getting Started](#-getting-started)
   - [Prerequisites](#prerequisites)
   - [Installation](#installation)
   - [Pricing Cache Synchronization](#pricing-cache-synchronization)
5. [Usage & Host Integration](#-usage--host-integration)
   - [Running Stdio Server](#running-stdio-server)
   - [Running HTTP/SSE Server](#running-httpsse-server)
   - [Claude Desktop Configuration](#claude-desktop-configuration)
   - [Cursor Configuration](#cursor-configuration)
   - [Gemini CLI Configuration](#gemini-cli-configuration)
6. [MCP Primitive Reference](#-mcp-primitive-reference)
   - [Tools](#1-tools-actions)
   - [Resources](#2-resources-contexts)
   - [Prompts](#3-prompts-reusable-workflows)
7. [Development & Contributing](#-development--contributing)
8. [License & Disclaimer](#-license--disclaimer)

---

## ⚡ Core Principles

* **Deterministic Core:** No randomness, no live network dependencies on estimation paths. Same input + same database snapshot = identical output.
* **Library-First Design:** All estimation, pricing, HCL parsing, and rendering logic lives in the transport-agnostic `src/gcp_billing_mcp/core` library. MCP and HTTP layers are thin adapters.
* **List Price Only:** Prices represent official list prices. Disclaimers are attached explaining that SUD/CUD/EDP or negotiated discounts are not applied.
* **Fail Loud, Never Under-Report:** Unmappable, unsupported, or unpriced resources are surfaced in a top-level `unpriced[]` block instead of silently returning $0.00.
* **Extensible Registries:** Plug-and-play interfaces for cloud providers (`PricingProvider`), IaC formats (`IaCParser`), and report exporters (`OutputRenderer`).

---

## 🛠 Supported Services (v1)

* **Compute Engine (GCE):** VM instances with vCPU & RAM pricing (standard types like `n1`, `n2`, `e2` or `custom-vcpus-memory` specs).
* **Cloud Storage (GCS):** Standard, Nearline, Coldline, and Archive storage classes across regional, dual-region, and multi-region locations. Estimates storage, Class A/B operations, internet egress, and retrieval.
* **Google Kubernetes Engine (GKE):** Standard GKE clusters with cluster management fees and node pools decomposed dynamically into Compute Engine VMs and attached boot disks.
* **Cloud SQL:** Enterprise and Enterprise Plus editions for PostgreSQL, MySQL, and SQL Server databases. Models custom/standard tiers, HA (regional/zonal), SSD/HDD storage, and backup storage.
* **BigQuery:** Datasets with active and long-term storage, query scan volume (on-demand), and legacy streaming inserts.
* **Attached Storage:** Boot disks and persistent volumes:
  * Standard Persistent Disks (`pd-standard` / `pd_persistent_disk`)
  * SSD Persistent Disks (`pd-ssd` / `ssd_persistent_disk`)
* **Network Egress:** Exposes hooks for egress mapping.
* **IaC Parsers:**
  * **Static Terraform Parser:** Parse `.tf` HCL files without needing the `terraform` binary (falls back dynamically and reports unresolved variables).
  * **Plan JSON Parser:** Parse full Terraform plan JSONs (`terraform show -json`) with fully resolved dynamic variables, modules, and counts.

---

## 📐 Architecture Overview

```
                 MCP Hosts (NLU, Orchestration & Explanation)
         ┌───────────────────────────────────────────────────────────┐
         │ Claude Code  ·  Gemini CLI  ·  Claude Desktop  ·  Cursor  │
         └─────────────────────────────┬─────────────────────────────┘
                                       │
                                       │ MCP (stdio / HTTP+SSE, Bearer)
                                       ▼
         ┌───────────────────────────────────────────────────────────┐
         │                  GCP Billing MCP Server                   │  ◀── Thin Adapter
         │       Tools   ·   Resources   ·   Prompts Primitives      │
         └─────────────────────────────┬─────────────────────────────┘
                                       │
                                       │ In-Process Calls
                                       ▼
         ┌───────────────────────────────────────────────────────────┐
         │                       Core Library                        │
         │  Cloud-Neutral Resource Model & Strict Schema Validation  │
         │  Registries: IaCParser · PricingProvider · OutputRenderer │
         └──────────────┬──────────────────────────────┬─────────────┘
                        │                              │
                        ▼                              ▼
             ┌─────────────────────┐        ┌──────────────────────┐
             │    Pricing Cache    │        │     Refresh Job      │
             │   SQLite Database   │◀───────│   (72-hour Cadence)  │
             │  provider·sku·price │        │ Atomic snapshot swap │
             └─────────────────────┘        └──────────┬───────────┘
                                                       │
                                                       ▼
                                            ┌──────────────────────┐
                                            │  GCP Cloud Billing   │
                                            │ Pricing API / Groups │
                                            └──────────────────────┘
```

---

## 🚀 Getting Started

### Prerequisites
* **Python:** `>= 3.14` (as defined in `pyproject.toml`)
* **Package Manager:** [uv](https://github.com/astral-sh/uv) (strongly recommended)
* **Google Cloud SDK (Optional):** Used to authenticate cache refreshes if no explicit API keys are supplied.

### Installation
Clone the repository and install all dependencies:
```bash
# Clone the repository
git clone https://github.com/your-org/gcp-billing-mcp.git
cd gcp-billing-mcp

# Sync dependencies and build virtual environment
uv sync
```

### Pricing Cache Synchronization
Before estimating costs, the SQLite database cache needs to be seeded with GCP SKU list prices. The caching layer runs on a 72-hour refresh cadence.

To fetch and cache prices, authenticate with GCP using one of three methods:
1. **Application Default Credentials:** The fetcher runs `gcloud auth print-access-token` in the background.
2. **Access Token:** Set `GCP_ACCESS_TOKEN`.
3. **API Key:** Set `GCP_API_KEY`.

Execute the cache refresh:
```bash
# Run cache refresh tool manually through Python module
GCP_API_KEY="your-key-here" uv run python -c "
from gcp_billing_mcp.core.pricing.gcp_fetch import refresh_pricing_cache
from gcp_billing_mcp.mcp.server import get_default_db_path
print(refresh_pricing_cache(get_default_db_path(), force=True))
"
```

---

## 🔌 Usage & Host Integration

### Running Stdio Server
To launch the MCP server over stdio for local hosts (like Claude Code or Claude Desktop):
```bash
uv run python -m gcp_billing_mcp.mcp.server
```

### Running HTTP/SSE Server
To run a high-performance SSE (Server-Sent Events) HTTP server wrapping the MCP protocol with Bearer Auth:
```bash
# Set your token and launch via uvicorn
export GCP_BILLING_BEARER_TOKEN="your-secure-token"
uv run uvicorn gcp_billing_mcp.http.app:create_app --factory --port 8000
```

---

### Claude Desktop Configuration
Add the server to your Claude Desktop configuration file (typically `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "gcp-billing-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/gcp-billing-mcp",
        "run",
        "python",
        "-m",
        "gcp_billing_mcp.mcp.server"
      ],
      "env": {
        "GCP_API_KEY": "your-optional-api-key"
      }
    }
  }
}
```

---

### Cursor Configuration
1. Open Cursor Settings -> **Features** -> **MCP**.
2. Click **+ Add New MCP Server**.
3. Fill in the fields:
   * **Name:** `gcp-billing-mcp`
   * **Type:** `command`
   * **Command:** `uv --directory /absolute/path/to/gcp-billing-mcp run python -m gcp_billing_mcp.mcp.server`

---

### Gemini CLI Configuration
Add the server execution line to your Gemini CLI configuration block:
```yaml
mcpServers:
  gcp-billing:
    command: "uv"
    args:
      - "--directory"
      - "/absolute/path/to/gcp-billing-mcp"
      - "run"
      - "python"
      - "-m"
      - "gcp_billing_mcp.mcp.server"
```

---

## 🛠 MCP Primitive Reference

### 1. Tools (Actions)
Deterministic execution functions exposed to the host LLM:

| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `parse_terraform` | `path: str, mode: str = "auto"` | Parses HCL files or plan JSON from a folder to extract a `ResourceModel`. |
| `validate_resource_model` | `model: ResourceModel` | Validates a parsed resource model against schemas. |
| `estimate_infrastructure` | `model: ResourceModel` | Resolves SKUs, maps pricing, and returns a detailed `Estimate`. |
| `render_estimate` | `estimate: Estimate, format: str` | Renders a generated estimate to `json`, `csv`, or `markdown`. |
| `get_cache_status` | `provider: str = "gcp"` | Retrieves SQLite pricing SKU counts and freshness age. |
| `refresh_pricing_cache`| `provider: str = "gcp", force: bool = False` | Fetches fresh SKU rates from the GCP Billing API. |
| `compare_regions` | `model: ResourceModel, regions: list[str]` | Prices the resource model across multiple regions to identify the cheapest. |
| `compare_estimates` | `estimate_a: Estimate, estimate_b: Estimate` | Compares two estimates and outputs a line-by-line cost diff. |
| `what_if` | `model: ResourceModel, changes: dict` | Simulates cost impacts by applying structural modifications to a model. |
| `suggest_cheaper_machine_types` | `resource: Resource` | Searches GCE catalog to find cheaper alternative configurations. |
| `find_unpriced` | `model: ResourceModel` | Scans a model to list any unpriced or unsupported resource mappings. |

---

### 2. Resources (Contexts)
Static and dynamic datasets the host LLM can read:

* `schema://resource-model`: The JSON schema defining the canonical cloud-neutral resource model. Used by LLMs to format natural language resource descriptions correctly.
* `catalog://coverage`: Text description listing supported GCP services, resources, and storage items.
* `catalog://defaults`: Standard baseline assumptions (e.g., 730 runtime hours per month if omitted).
* `pricing://snapshot`: Metadata summary of the current local SQLite pricing database.
* `docs://disclaimer`: Standing cost calculation disclaimer (List Price Only).

---

### 3. Prompts (Reusable Workflows)
Pre-packaged workflow templates helping the host orchestrate calls:

* `estimate-from-description`: Prompts the LLM to extract a resource model from free text, validate it, estimate it, and output a markdown table.
* `estimate-from-terraform`: Prompts the LLM to locate Terraform configuration, parse it, run the estimation, and render a breakdown.
* `explain-estimate`: Prompts the LLM to inspect an estimate JSON payload and highlight major cost drivers.
* `optimize-cost`: Guides the LLM to suggest regional migrations or cheaper VM classes.

---

## 🧪 Development & Contributing

The codebase is built using **TDD (Test-Driven Development) driven by behavior (BDD)**. All production additions require a preceding failing test.

### Running Quality Checks
Always run these checks before proposing any modifications:

```bash
# Run full test suite (unit and mocked API tests)
uv run pytest

# Run tests with coverage reporting (Target: >=90% branch coverage on core/)
uv run pytest --cov=gcp_billing_mcp --cov-branch

# Run type checker (strict mode enabled)
uv run mypy src

# Run linter and check formatting
uv run ruff check .
uv run ruff format .
```

### Integration Tests
To run integration tests that query the live GCP Cloud Billing API (requires network and active GCP credentials):
```bash
uv run pytest -m integration
```

---

## ⚖ License & Disclaimer

This project is licensed under the Apache License 2.0. See the [LICENSE](file:///Users/zhhuta/Projects/Development/LLM_and_AI/gcp-billing-mcp/LICENSE) file for details.

> [!WARNING]
> **List Price Disclaimer:** Estimates generated by this tool are calculated using Google Cloud list prices. They do not account for Sustained Use Discounts (SUD), Committed Use Discounts (CUD), custom negotiated contracts (EDP), free tiers, or promotional credits. Actual invoice costs may vary.
