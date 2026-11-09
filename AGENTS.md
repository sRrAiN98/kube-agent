# AGENTS.md

Welcome, AI Agent! This file contains machine-readable instructions, architecture maps, and operating guidelines for developing, installing, and maintaining `kube-agent`.

---

## 1. Quick Installation for Agents

To install and verify `kube-agent` in your working environment, run:

```bash
# 1. Install dependencies in editable mode
pip install -e ".[dev]"

# 2. Verify CLI binary
kube-agent --help

# 3. Run full test suite (82 tests must pass)
pytest

# 4. Check lint
ruff check .
```

For complete automated installation playbooks (Docker, Helm, In-Cluster, Server daemon, Batch CronJob), read [`docs/agent-installation.md`](docs/agent-installation.md).

---

## 2. Core Architecture & Modules

```
src/kube_agent/
├── main.py              # Click CLI entrypoint (subcommands: chat, serve, batch)
├── agent.py             # Core Agent loop, tool dispatcher, circuit breaker, autonomy
├── server.py            # aiohttp REST API & Alertmanager Webhook daemon (/healthz, /api/v1/*)
├── batch.py             # Zero-token heuristic healthcheck & selective LLM remediation
├── config.py            # Hierarchical config (CLI > Env > kube-agent.yaml > Defaults)
├── safety.py            # Safety guardrails (Strict, Permissive, Disabled, Read-Only)
├── tools.py             # 34 tool definitions and handlers
├── kubernetes_ops.py    # K8s operations + k8s_diagnose_cluster
├── observability_ops.py # Prometheus PromQL & Grafana Loki LogQL client
├── gitea_ops.py         # Gitea REST API & Git operations
├── helm_ops.py          # Helm CLI wrapper (lint, template, upgrade, rollback)
├── file_ops.py          # Sandboxed file operations (/tmp, /home/agent)
├── context.py           # Context window compaction and tool result summarization
└── cli.py               # Rich terminal formatting & token streaming
```

---

## 3. The 3 Operational Modes

1. **Interactive Chat Mode (`kube-agent` or `kube-agent chat`)**:
   - Interactive terminal shell for human engineers and interactive agent sessions.
   - Run with `--read-only` to strictly block any state mutations.
2. **Realtime Server Mode (`kube-agent serve --port 8080`)**:
   - `GET  /healthz`: Health probe
   - `POST /api/v1/chat`: JSON prompt execution
   - `POST /api/v1/diagnose`: Cluster diagnosis
   - `POST /api/v1/webhook`: Alertmanager / Grafana webhook receiver for automated RCA
3. **AI Cost-Optimized Batch Mode (`kube-agent batch`)**:
   - **Zero-Token Pre-flight**: Evaluates cluster with rule-based heuristics. If healthy, uses **0 AI tokens ($0.00)**.
   - **Selective LLM RCA**: If issues detected, invokes LLM for root cause analysis and outputs reports to `--report-dir`.
   - `--auto-fix`: Executes safe autonomous remediation (unless read-only).
   - `--interval <sec>`: Runs continuous monitoring loop.

---

## 4. Development & Contribution Rules

- **Code Standards**:
  - Python 3.11+ syntax (`from __future__ import annotations`, modern type unions `X | Y`).
  - Formatter / Linter: `ruff check .` with `line-length = 120`. Must pass with 0 errors.
  - Tests: `pytest` must pass 100% of tests.
- **Strict Constraints**:
  - Maintain documentation integrity.
  - **NEVER** generate, commit, or push planning artifacts such as `ralph-prd.json` or `RALPH_ROADMAP.md`.
  - Always link files with markdown links (`file:///...` or relative markdown links).
