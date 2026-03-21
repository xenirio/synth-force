#!/usr/bin/env python
import json
import re
import sys
import warnings

from crewai.flow.flow import Flow, listen, or_, router, start

from synth_force.crews.analysis_crew.analysis_crew import AnalysisCrew
from synth_force.crews.devops_crew.devops_crew import DevOpsCrew
from synth_force.crews.engineering_crew.engineering_crew import EngineeringCrew
from synth_force.crews.qa_crew.qa_crew import QACrew
from synth_force.state import EpicTask, SynthForceState, Ticket
from synth_force.tools.k8s_tools import (
    AnalyzeRepoStructureTool,
    CommitWorkflowTool,
    GenerateWorkflowTool,
)

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")


def _parse_json(raw: str):
    """Extract and parse JSON from LLM output that may contain extra text."""
    # Strip markdown code fences first
    cleaned = re.sub(r'```(?:json)?\s*', '', raw).strip()
    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Try to find JSON array or object in the text
    for pattern in [r'\[.*\]', r'\{.*\}']:
        match = re.search(pattern, cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                continue
    raise ValueError(f"Could not parse JSON from LLM output: {raw[:500]}")


class SynthForceFlow(Flow[SynthForceState]):
    """Multi-agent software development pipeline orchestrated as a CrewAI Flow."""

    @start()
    def analyze_epic(self):
        """Phase 1: System Analyst reads the epic and creates task issues."""
        result = (
            AnalysisCrew()
            .crew()
            .kickoff(
                inputs={
                    "repo_full_name": f"{self.state.repo_owner}/{self.state.repo_name}",
                    "epic_issue_number": self.state.epic_url.split("/")[-1],
                }
            )
        )
        raw_tasks = _parse_json(result.raw)
        if isinstance(raw_tasks, dict):
            raw_tasks = [raw_tasks]
        self.state.tasks = [EpicTask(**t) for t in raw_tasks]
        print(f"[ANALYSIS] Created {len(self.state.tasks)} task(s)")
        for t in self.state.tasks:
            print(f"  - #{t.issue_number}: {t.title}")
        return self.state.tasks

    @listen(analyze_epic)
    def setup_ci(self):
        """Ensure CI workflow exists on main before PRs are created."""
        repo_full_name = f"{self.state.repo_owner}/{self.state.repo_name}"
        print(f"[CI SETUP] Detecting app type for {repo_full_name}")

        # Detect app type
        analysis = AnalyzeRepoStructureTool()._run(repo_full_name)
        has_package_json = "package.json" in analysis and "Detected config files:" in analysis
        has_python = any(
            kw in analysis
            for kw in ["requirements.txt", "pyproject.toml", "PYTHON_APP"]
        )

        # Choose CI template
        if has_package_json:
            ci_platform = "ci-node"
        elif has_python:
            ci_platform = "ci-python"
        else:
            ci_platform = "ci-node"  # safe default

        print(f"[CI SETUP] Using {ci_platform} template")

        # Generate and commit CI workflow to main
        ci_content = GenerateWorkflowTool()._run(ci_platform)
        result = CommitWorkflowTool()._run(
            repo_full_name=repo_full_name,
            workflow_filename="ci.yml",
            workflow_content=ci_content,
            branch="main",
            commit_message="ci: add CI workflow for pull requests",
        )
        print(f"[CI SETUP] {result}")

    @listen(setup_ci)
    def engineer_tasks(self):
        """Phase 2: For each task, create ticket, implement code, and review.

        Uses two SE agents to process tickets in parallel (pairs).
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        all_tickets = []
        repo_full_name = f"{self.state.repo_owner}/{self.state.repo_name}"

        def _process_task(task):
            print(f"[ENGINEERING] Working on task #{task.issue_number}")
            ticket_result = (
                EngineeringCrew()
                .crew()
                .kickoff(
                    inputs={
                        "repo_full_name": repo_full_name,
                        "task_issue_number": task.issue_number,
                    }
                )
            )
            ticket_data = _parse_json(ticket_result.raw)
            return Ticket(
                issue_number=ticket_data.get("issue_number", 0),
                issue_url=ticket_data.get("issue_url", ""),
                title=ticket_data.get("title", ""),
                pr_url=ticket_data.get("pr_url", ""),
                pr_number=ticket_data.get("pr_number", 0),
                review_status=ticket_data.get("review_status", ""),
                ci_status=ticket_data.get("ci_status", ""),
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(_process_task, task): task
                for task in self.state.tasks
            }
            for future in as_completed(futures):
                task = futures[future]
                try:
                    ticket = future.result()
                    all_tickets.append(ticket)
                except Exception as e:
                    print(f"[ENGINEERING] Task #{task.issue_number} failed: {e}")

        self.state.tickets = all_tickets
        return all_tickets

    @router(engineer_tasks)
    def check_reviews(self):
        """Route based on review and CI outcomes."""
        all_approved = all(
            t.review_status == "approved"
            and t.ci_status in ("all_passed", "passed", "pending", "")
            for t in self.state.tickets
        )
        if all_approved:
            return "qa_ready"
        return "review_failed"

    @listen("review_failed")
    def handle_review_failure(self):
        """Handle tickets that need rework after review rejection."""
        # Phase 5 will implement rework loops.
        # For now, log and continue to QA with whatever was approved.
        failed = [
            t for t in self.state.tickets if t.review_status != "approved"
        ]
        for t in failed:
            print(f"[REWORK NEEDED] Ticket #{t.issue_number}: {t.title}")

    @listen(or_("qa_ready", handle_review_failure))
    def run_qa(self):
        """Phase 3: QA tests each PR via Playwright browser testing."""
        if "qa" in self.state.skip_phases:
            print("[QA] Skipped (--skip qa)")
            for ticket in self.state.tickets:
                ticket.qa_status = "skipped"
            return self.state.tickets

        repo_full_name = f"{self.state.repo_owner}/{self.state.repo_name}"

        for ticket in self.state.tickets:
            if not ticket.pr_number:
                continue
            print(f"[QA] Testing PR #{ticket.pr_number} for ticket #{ticket.issue_number}")
            qa_result = (
                QACrew()
                .crew()
                .kickoff(
                    inputs={
                        "repo_full_name": repo_full_name,
                        "pr_number": ticket.pr_number,
                        "ticket_issue_number": ticket.issue_number,
                    }
                )
            )
            result_data = _parse_json(qa_result.raw)
            ticket.qa_status = result_data.get("qa_status", "unknown")

        return self.state.tickets

    @router(run_qa)
    def check_qa(self):
        """Route based on QA outcomes."""
        if "qa" in self.state.skip_phases:
            return "deploy_ready"
        all_passed = all(
            t.qa_status == "passed"
            for t in self.state.tickets
            if t.pr_number
        )
        if all_passed:
            return "deploy_ready"
        return "qa_failed"

    @listen("qa_failed")
    def handle_qa_failure(self):
        """Rework tickets that failed QA — up to 2 attempts per ticket."""
        repo_full_name = f"{self.state.repo_owner}/{self.state.repo_name}"
        max_rework = 2

        for ticket in self.state.tickets:
            if ticket.qa_status != "failed" or not ticket.pr_number:
                continue

            for attempt in range(1, max_rework + 1):
                print(f"[REWORK {attempt}/{max_rework}] Ticket #{ticket.issue_number}: {ticket.title}")
                rework_result = (
                    EngineeringCrew()
                    .crew()
                    .kickoff(inputs={
                        "repo_full_name": repo_full_name,
                        "task_issue_number": ticket.issue_number,
                    })
                )
                rework_data = _parse_json(rework_result.raw)
                new_pr = rework_data.get("pr_number", 0)
                if not new_pr:
                    print(f"  → Rework produced no PR, skipping")
                    break

                ticket.pr_number = new_pr
                ticket.pr_url = rework_data.get("pr_url", "")
                print(f"  → New PR #{new_pr}, running QA...")

                qa_result = (
                    QACrew()
                    .crew()
                    .kickoff(inputs={
                        "repo_full_name": repo_full_name,
                        "pr_number": new_pr,
                        "ticket_issue_number": ticket.issue_number,
                    })
                )
                qa_data = _parse_json(qa_result.raw)
                ticket.qa_status = qa_data.get("qa_status", "unknown")
                print(f"  → QA: {ticket.qa_status}")

                if ticket.qa_status == "passed":
                    break

            if ticket.qa_status == "failed":
                print(f"  ⚠ Ticket #{ticket.issue_number} still failing after {max_rework} rework attempts")

    @listen(or_("deploy_ready", handle_qa_failure))
    def deploy(self):
        """Phase 4: Analyze repo, set up CI/CD, and create release."""
        if "devops" in self.state.skip_phases:
            print("[DEVOPS] Skipped (--skip devops)")
            return {"deployment_status": "skipped", "platform": "skipped"}

        repo_full_name = f"{self.state.repo_owner}/{self.state.repo_name}"
        ticket_summaries = "; ".join(
            f"#{t.issue_number} {t.title}" for t in self.state.tickets
        )
        release_tag = self.state.release_tag or "v0.1.0"

        print(f"[DEVOPS] Analyzing repo and setting up CI/CD for {repo_full_name}")
        result = (
            DevOpsCrew()
            .crew()
            .kickoff(
                inputs={
                    "repo_full_name": repo_full_name,
                    "release_tag": release_tag,
                    "release_name": f"Release {release_tag}",
                    "ticket_summaries": ticket_summaries,
                }
            )
        )
        result_data = _parse_json(result.raw)
        self.state.deployment_status = result_data.get(
            "deployment_status", "unknown"
        )
        print(f"[DEVOPS] Platform: {result_data.get('platform', '?')}")
        print(f"[DEVOPS] Status: {self.state.deployment_status}")

        # Close the epic issue
        epic_number = int(self.state.epic_url.rstrip("/").split("/")[-1])
        from synth_force.tools.github_tools import GitHubUpdateIssueTool
        GitHubUpdateIssueTool()._run(
            repo_full_name=repo_full_name,
            issue_number=epic_number,
            comment=f"All tasks completed. Released as {release_tag}.",
            state="closed",
        )
        print(f"[DEVOPS] Closed epic #{epic_number}")

        return result_data


def run():
    """Run the flow.

    Usage: synth_force <epic_issue_url> [--skip qa] [--skip devops]
    """
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    epic_url = args[0] if args else ""
    if not epic_url:
        print("Usage: synth_force <epic_issue_url> [--skip qa] [--skip devops]")
        print("  e.g. synth_force https://github.com/owner/repo/issues/1 --skip qa")
        sys.exit(1)

    # Parse --skip flags
    skip_phases = []
    skip_next = False
    for a in sys.argv[1:]:
        if skip_next:
            skip_phases.append(a.lower())
            skip_next = False
        elif a == "--skip":
            skip_next = True

    # Parse owner/repo from URL
    parts = epic_url.rstrip("/").split("/")
    # Expected: https://github.com/{owner}/{repo}/issues/{number}
    owner = parts[-4]
    repo = parts[-3]

    if skip_phases:
        print(f"[CONFIG] Skipping phases: {', '.join(skip_phases)}")

    flow = SynthForceFlow()
    flow.state.repo_owner = owner
    flow.state.repo_name = repo
    flow.state.epic_url = epic_url
    flow.state.skip_phases = skip_phases
    flow.kickoff()


def _ensure_ci_workflow(repo_full_name: str):
    """Commit ci.yml to main if it doesn't already exist."""
    from synth_force.tools.github_tools import GitHubReadFileContentTool

    existing = GitHubReadFileContentTool()._run(
        repo_full_name, ".github/workflows/ci.yml", "main"
    )
    if not existing.startswith("Error"):
        print(f"[CI SETUP] ci.yml already exists on main")
        return

    print(f"[CI SETUP] Setting up CI workflow for {repo_full_name}")
    analysis = AnalyzeRepoStructureTool()._run(repo_full_name)
    has_package_json = "package.json" in analysis and "Detected config files:" in analysis
    has_python = any(
        kw in analysis for kw in ["requirements.txt", "pyproject.toml", "PYTHON_APP"]
    )
    ci_platform = "ci-node" if has_package_json else ("ci-python" if has_python else "ci-node")
    ci_content = GenerateWorkflowTool()._run(ci_platform)
    result = CommitWorkflowTool()._run(
        repo_full_name=repo_full_name,
        workflow_filename="ci.yml",
        workflow_content=ci_content,
        branch="main",
        commit_message="ci: add CI workflow for pull requests",
    )
    print(f"[CI SETUP] {result}")


def _merge_pr_safe(repo_full_name: str, pr_number: int):
    """Merge a PR, catching errors gracefully."""
    from synth_force.tools.github_tools import GitHubMergePRTool
    try:
        result = GitHubMergePRTool()._run(repo_full_name, pr_number, merge_method="squash")
        print(f"  {result}")
        return True
    except Exception as e:
        print(f"  Failed to merge PR #{pr_number}: {e}")
        return False


def continue_work():
    """Scan repo for open issues and route them to the appropriate crew.

    Usage: synth_continue <repo> [--dry-run]
    """
    import os

    from github import Auth, Github

    if len(sys.argv) < 2:
        print("Usage: synth_continue <repo> [--dry-run]")
        print("  repo: owner/repo or GitHub URL")
        print()
        print("Scans open issues and routes them:")
        print("  'task' label + no linked ticket  → Engineering crew")
        print("  'ticket' label + no PR           → Engineering crew")
        print("  'qa-failed' label                → Engineering crew (rework)")
        print("  'ticket' + has PR + no QA label  → QA crew")
        sys.exit(1)

    repo_arg = sys.argv[1]
    dry_run = "--dry-run" in sys.argv
    repo_full_name = _parse_repo(repo_arg)

    token = os.environ.get("GITHUB_TOKEN", "")
    g = Github(auth=Auth.Token(token))
    repo = g.get_repo(repo_full_name)

    # Ensure CI workflow exists on main before engineering
    _ensure_ci_workflow(repo_full_name)

    # Collect open issues by label
    issues = list(repo.get_issues(state="open"))
    tasks_to_engineer = []
    tickets_to_engineer = []
    tickets_to_qa = []
    tickets_to_rework = []

    # Pre-fetch all PRs once to avoid repeated API calls
    all_prs = list(repo.get_pulls(state="all"))

    # Build sets for dedup: issue numbers that already have tickets or PRs
    all_issue_bodies = {
        i.number: (i.body or "") for i in issues if not i.pull_request
    }
    ticket_issue_numbers = {
        i.number for i in issues
        if not i.pull_request and "ticket" in [l.name for l in i.labels]
    }

    def _task_has_ticket(task_issue):
        """Check if a task already has a linked ticket issue."""
        for num, body in all_issue_bodies.items():
            if num == task_issue.number:
                continue
            # Ticket body or title references the task number
            if f"#{task_issue.number}" in body:
                return True
        return False

    def _find_open_pr(issue_number):
        """Find an open PR that references this issue."""
        for pr in all_prs:
            if pr.state != "open":
                continue
            # Check PR body reference or branch name
            if (pr.body and f"#{issue_number}" in pr.body) or \
               pr.head.ref == f"feature/ticket-{issue_number}":
                return pr.number
        return 0

    def _has_merged_pr(issue_number):
        """Check if this issue already has a merged PR."""
        for pr in all_prs:
            if pr.state != "closed" or not pr.merged_at:
                continue
            if (pr.body and f"#{issue_number}" in pr.body) or \
               pr.head.ref == f"feature/ticket-{issue_number}":
                return True
        return False

    for issue in issues:
        if issue.pull_request:
            continue
        labels = [l.name for l in issue.labels]

        if "qa-failed" in labels:
            tickets_to_rework.append(issue)
        elif "task" in labels:
            if _task_has_ticket(issue):
                print(f"  [SKIP] Task #{issue.number} already has a ticket")
                continue
            tasks_to_engineer.append(issue)
        elif "ticket" in labels:
            if "qa-passed" in labels:
                continue  # already done
            if _has_merged_pr(issue.number):
                print(f"  [SKIP] Ticket #{issue.number} already has a merged PR")
                continue
            open_pr = _find_open_pr(issue.number)
            if open_pr and "qa-failed" not in labels:
                tickets_to_qa.append(issue)
            elif not open_pr:
                tickets_to_engineer.append(issue)

    print(f"Repository: {repo_full_name}")
    print(f"Open issues: {len(issues)}")
    print()

    if tasks_to_engineer:
        print(f"Tasks needing engineering ({len(tasks_to_engineer)}):")
        for i in tasks_to_engineer:
            print(f"  #{i.number}: {i.title}")

    if tickets_to_engineer:
        print(f"Tickets needing implementation ({len(tickets_to_engineer)}):")
        for i in tickets_to_engineer:
            print(f"  #{i.number}: {i.title}")

    if tickets_to_rework:
        print(f"Tickets needing rework ({len(tickets_to_rework)}):")
        for i in tickets_to_rework:
            print(f"  #{i.number}: {i.title}")

    if tickets_to_qa:
        print(f"Tickets needing QA ({len(tickets_to_qa)}):")
        for i in tickets_to_qa:
            print(f"  #{i.number}: {i.title}")

    total = len(tasks_to_engineer) + len(tickets_to_engineer) + len(tickets_to_rework) + len(tickets_to_qa)
    if total == 0:
        print("Nothing to do — all issues are complete or not actionable.")
        return

    if dry_run:
        print("\n[DRY RUN] Would process the above. Remove --dry-run to execute.")
        return

    print(f"\nProcessing {total} items...\n")

    max_rework = 2

    def _run_qa(repo_name, pr_num, ticket_num):
        """Run QA and return status."""
        print(f"  [QA] Testing PR #{pr_num} for ticket #{ticket_num}")
        qa_result = QACrew().crew().kickoff(inputs={
            "repo_full_name": repo_name,
            "pr_number": pr_num,
            "ticket_issue_number": ticket_num,
        })
        qa_data = _parse_json(qa_result.raw)
        status = qa_data.get("qa_status", "unknown")
        print(f"  → QA: {status}")
        return status

    def _engineer_and_qa(repo_name, issue_number, label, rework_count=0):
        """Run engineering → QA with rework loop."""
        print(f"  [{'REWORK ' + str(rework_count) if rework_count else 'ENGINEERING'}] "
              f"#{issue_number} ({label})")
        result = EngineeringCrew().crew().kickoff(inputs={
            "repo_full_name": repo_name,
            "task_issue_number": issue_number,
        })
        ticket_data = _parse_json(result.raw)
        pr_number = ticket_data.get("pr_number", 0)
        ticket_number = ticket_data.get("issue_number", issue_number)
        print(f"  → Ticket #{ticket_number}, PR #{pr_number}")

        if not pr_number:
            print(f"  → No PR created, skipping QA")
            return

        qa_status = _run_qa(repo_name, pr_number, ticket_number)

        # Rework loop
        attempt = 0
        while qa_status == "failed" and attempt < max_rework:
            attempt += 1
            print(f"\n  [REWORK {attempt}/{max_rework}] "
                  f"Ticket #{ticket_number} failed QA, sending back to engineering...")
            result = EngineeringCrew().crew().kickoff(inputs={
                "repo_full_name": repo_name,
                "task_issue_number": ticket_number,
            })
            rework_data = _parse_json(result.raw)
            new_pr = rework_data.get("pr_number", 0)
            if not new_pr:
                print(f"  → Rework produced no PR, stopping")
                break
            pr_number = new_pr
            print(f"  → Rework PR #{pr_number}")
            qa_status = _run_qa(repo_name, pr_number, ticket_number)

        if qa_status == "failed":
            print(f"  ⚠ Ticket #{ticket_number} still failing after {max_rework} rework attempts")

        # Merge the latest PR if QA passed
        if qa_status == "passed" and pr_number:
            print(f"  [MERGE] QA passed, merging PR #{pr_number}")
            _merge_pr_safe(repo_name, pr_number)

    # 1. Tasks that need tickets + implementation + QA
    for issue in tasks_to_engineer:
        print(f"\n[TASK] #{issue.number}: {issue.title}")
        _engineer_and_qa(repo_full_name, issue.number, "task")

    # 2. Tickets without PRs
    for issue in tickets_to_engineer:
        print(f"\n[TICKET] #{issue.number}: {issue.title}")
        _engineer_and_qa(repo_full_name, issue.number, "ticket")

    # 3. Rework: qa-failed tickets
    for issue in tickets_to_rework:
        print(f"\n[REWORK] #{issue.number}: {issue.title}")
        _engineer_and_qa(repo_full_name, issue.number, "rework")

    # 4. QA only: tickets with PRs but no QA status
    for issue in tickets_to_qa:
        pr_number = _find_open_pr(issue.number)
        if not pr_number:
            continue
        print(f"\n[QA ONLY] #{issue.number}: {issue.title}")
        qa_status = _run_qa(repo_full_name, pr_number, issue.number)

        # Rework if QA fails
        attempt = 0
        while qa_status == "failed" and attempt < max_rework:
            attempt += 1
            print(f"\n  [REWORK {attempt}/{max_rework}] Sending back to engineering...")
            result = EngineeringCrew().crew().kickoff(inputs={
                "repo_full_name": repo_full_name,
                "task_issue_number": issue.number,
            })
            rework_data = _parse_json(result.raw)
            new_pr = rework_data.get("pr_number", 0)
            if not new_pr:
                break
            qa_status = _run_qa(repo_full_name, new_pr, issue.number)
            pr_number = new_pr

        # Merge after QA passes
        if qa_status == "passed":
            print(f"  [MERGE] QA passed, merging PR #{pr_number}")
            _merge_pr_safe(repo_full_name, pr_number)

    print("\nDone!")


def train():
    """Train the crew for a given number of iterations."""
    inputs = {
        "repo_full_name": "owner/repo",
        "epic_issue_number": "1",
    }
    AnalysisCrew().crew().train(
        n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=inputs
    )


def replay():
    """Replay the crew execution from a specific task."""
    AnalysisCrew().crew().replay(task_id=sys.argv[1])


def test():
    """Test the crew execution."""
    inputs = {
        "repo_full_name": "owner/repo",
        "epic_issue_number": "1",
    }
    AnalysisCrew().crew().test(
        n_iterations=int(sys.argv[1]), eval_llm=sys.argv[2], inputs=inputs
    )


def _parse_repo(repo_arg: str) -> str:
    """Parse 'owner/repo' from a GitHub URL or 'owner/repo' string."""
    if "github.com" in repo_arg:
        parts = repo_arg.rstrip("/").split("/")
        # https://github.com/owner/repo/...
        idx = parts.index("github.com")
        return f"{parts[idx + 1]}/{parts[idx + 2]}"
    return repo_arg


def run_crew():
    """Run a single crew against a repo.

    Usage: synth_crew <crew> <repo> [key=value ...]
      crew: analysis | engineering | qa | devops
      repo: owner/repo or GitHub URL
    """
    if len(sys.argv) < 3:
        print("Usage: synth_crew <crew> <repo> [key=value ...]")
        print("  crew: analysis | engineering | qa | devops")
        print("  repo: owner/repo or https://github.com/owner/repo")
        print()
        print("Examples:")
        print("  synth_crew devops xenirio/trader-board")
        print("  synth_crew devops xenirio/trader-board release_tag=v0.2.0")
        print("  synth_crew analysis xenirio/trader-board task_issue_number=5")
        sys.exit(1)

    crew_name = sys.argv[1]
    repo_full_name = _parse_repo(sys.argv[2])

    # Parse extra key=value args
    extra = {}
    for arg in sys.argv[3:]:
        if "=" in arg:
            k, v = arg.split("=", 1)
            extra[k] = v

    crews = {
        "analysis": (AnalysisCrew, {
            "repo_full_name": repo_full_name,
            "epic_issue_number": extra.get("epic_issue_number", "1"),
        }),
        "engineering": (EngineeringCrew, {
            "repo_full_name": repo_full_name,
            "task_issue_number": int(extra.get("task_issue_number", "1")),
        }),
        "qa": (QACrew, {
            "repo_full_name": repo_full_name,
            "pr_number": int(extra.get("pr_number", "1")),
            "ticket_issue_number": int(extra.get("ticket_issue_number", "1")),
        }),
        "devops": (DevOpsCrew, {
            "repo_full_name": repo_full_name,
            "release_tag": extra.get("release_tag", "v0.1.0"),
            "release_name": extra.get("release_name", f"Release {extra.get('release_tag', 'v0.1.0')}"),
            "ticket_summaries": extra.get("ticket_summaries", ""),
        }),
    }

    if crew_name not in crews:
        print(f"Unknown crew: {crew_name}")
        print(f"Available: {', '.join(crews.keys())}")
        sys.exit(1)

    crew_cls, inputs = crews[crew_name]
    inputs.update(extra)

    # Ensure CI exists before engineering runs
    if crew_name == "engineering":
        _ensure_ci_workflow(repo_full_name)

    print(f"Running {crew_name} crew on {repo_full_name}")
    print(f"Inputs: {json.dumps(inputs, indent=2)}")
    result = crew_cls().crew().kickoff(inputs=inputs)
    print(f"\n{'='*60}")
    print(f"Result:\n{result.raw}")


def run_with_trigger():
    """Run the flow with trigger payload."""
    if len(sys.argv) < 2:
        raise RuntimeError("No trigger payload provided.")

    trigger_payload = json.loads(sys.argv[1])
    epic_url = trigger_payload.get("epic_url", "")
    if not epic_url:
        raise RuntimeError("Trigger payload must contain 'epic_url'")

    parts = epic_url.rstrip("/").split("/")
    owner = parts[-4]
    repo = parts[-3]

    flow = SynthForceFlow()
    flow.state.repo_owner = owner
    flow.state.repo_name = repo
    flow.state.epic_url = epic_url
    return flow.kickoff()
