# SynthForce

Multi-agent software development pipeline powered by [CrewAI](https://crewai.com). SynthForce reads a GitHub epic issue and autonomously breaks it into tasks, writes code, opens PRs, reviews, fixes CI failures, and deploys to Vercel.

## Pipeline

```
Epic (GitHub Issue)
  -> Analysis Crew: breaks epic into 1-3 task issues
    -> CI Setup: detects app type, commits ci.yml to main
      -> Engineering Crew (x2 parallel):
           Senior SE creates ticket
           SE writes code + opens PR
           Senior SE reviews + checks CI
           SE fixes CI failures
           Senior SE merges PR
        -> QA Crew: tests PRs (optional, skippable)
          -> DevOps Crew: commits deploy.yml, monitors pipeline, creates release
```

## Setup

Requires Python >=3.10 <3.14 and [uv](https://docs.astral.sh/uv/).

```bash
crewai install
```

### Environment Variables

Create a `.env` file:

```
MODEL=gemini/gemini-2.5-flash
GEMINI_API_KEY=your-key
GITHUB_TOKEN=your-github-pat-with-repo-scope
```

## Usage

### Run full pipeline

```bash
uv run synth_force <epic_issue_url>

# Skip QA and/or DevOps phases
uv run synth_force <epic_issue_url> --skip qa
uv run synth_force <epic_issue_url> --skip qa --skip devops
```

### Continue incomplete work

Scans open issues and routes them to the appropriate crew:

```bash
uv run synth_continue <owner/repo>
uv run synth_continue <owner/repo> --dry-run
```

### Run a single crew

```bash
uv run synth_crew <crew> <owner/repo> [key=value ...]

# Examples
uv run synth_crew analysis xenirio/trader-board epic_issue_number=1
uv run synth_crew engineering xenirio/trader-board task_issue_number=5
uv run synth_crew devops xenirio/trader-board release_tag=v0.2.0
```

### Reset target repo

```bash
uv run python scripts/reset_repo.py <owner/repo>
```

## Crews

| Crew | Agents | Role |
|------|--------|------|
| **Analysis** | System Analyst | Reads epic, creates task issues |
| **Engineering** | Senior SE, SE, SE 2 | Tickets, code, PRs, CI fixes, review, merge |
| **QA** | QA Engineer | Tests PRs (Playwright MCP - placeholder) |
| **DevOps** | DevOps Engineer | CI/CD workflows, deploy monitoring, releases |

## Project Structure

```
src/synth_force/
  main.py              # SynthForceFlow orchestrator + CLI commands
  state.py             # Flow state (Pydantic models)
  crews/
    analysis_crew/     # Epic -> task issues
    engineering_crew/  # Task -> ticket -> code -> PR -> merge
    qa_crew/           # PR testing
    devops_crew/       # CI/CD + deploy + release
  tools/
    github_tools.py    # PyGithub tools (issues, PRs, branches, files)
    k8s_tools.py       # Repo analysis, workflow generation, deploy monitoring
```
