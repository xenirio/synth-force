# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
crewai install          # Install/lock dependencies (uses uv internally)
crewai run              # Run the flow (prompts for epic URL)
uv run synth_force <epic_issue_url>  # Run directly with a GitHub epic URL
uv run train <n_iterations> <filename>
uv run replay <task_id>
```

No test framework is configured yet. Python files can be syntax-checked with `python3 -m py_compile <file>`.

## Architecture

This is a **CrewAI Flow** (`type = "flow"` in pyproject.toml) — not a single crew. The Flow orchestrates 4 crews in a pipeline that simulates a software development team working off GitHub Issues.

### Pipeline: `SynthForceFlow` (main.py)

```
Epic (GitHub Issue URL)
  → AnalysisCrew: System Analyst breaks epic into task issues
    → EngineeringCrew: Senior SE creates tickets, SE writes code + PR, Senior SE reviews
      → @router: review pass → QA, review fail → rework stub → QA
        → QACrew: QA tests PRs via Playwright, updates ticket labels
          → @router: QA pass → deploy, QA fail → failure stub → deploy
            → DevOpsCrew: Creates GitHub release, stubs K8s deploy
```

Flow state (`SynthForceState` in state.py) carries GitHub URLs, issue numbers, PR numbers, and statuses between stages. Routers (`check_reviews`, `check_qa`) emit string events (`"qa_ready"`, `"deploy_ready"`, `"review_failed"`, `"qa_failed"`) to control conditional branching.

### Crew pattern

Each crew follows the same structure under `src/synth_force/crews/<name>/`:
- `<name>.py` — `@CrewBase` class defining `@agent`, `@task`, and `@crew` methods
- `config/agents.yaml` — agent role/goal/backstory (interpolated via `{variable}` syntax)
- `config/tasks.yaml` — task description/expected_output with `{variable}` placeholders

Crews receive inputs as dicts passed to `.kickoff(inputs={...})`. The YAML placeholders must match the keys in those input dicts.

### Tools

All GitHub tools (`tools/github_tools.py`) use PyGithub with `GITHUB_TOKEN` from env. Each tool is a `crewai.tools.BaseTool` subclass with a Pydantic `args_schema`.

- `tools/browser_mcp_tool.py` — Playwright MCP placeholder (QA crew)
- `tools/k8s_tools.py` — Stubbed K8s/GCP deploy tools (DevOps crew)

### Incomplete / Stubbed

- **Rework loops**: `handle_review_failure` and `handle_qa_failure` in main.py just log and continue; Phase 5 should route back to engineering.
- **Playwright MCP**: `PlaywrightBrowserTool` returns placeholder text; needs real MCP server integration.
- **K8s deploy**: `KubernetesDeployTool` and `GCloudAuthTool` are stubs.
- **No `@persist`** on the Flow yet (crash recovery).
- **No guardrails, `max_iter`, or `max_execution_time`** on agents yet.

## Environment Variables

Configured in `.env`:
- `MODEL` — LLM model string (currently `gemini/gemini-1.5-flash`)
- `GEMINI_API_KEY` — Gemini API key
- `GITHUB_TOKEN` — GitHub PAT with repo scope (required for all GitHub tools)
