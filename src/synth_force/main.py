#!/usr/bin/env python
import json
import sys
import warnings

from crewai.flow.flow import Flow, listen, router, start

from synth_force.crews.analysis_crew.analysis_crew import AnalysisCrew
from synth_force.crews.devops_crew.devops_crew import DevOpsCrew
from synth_force.crews.engineering_crew.engineering_crew import EngineeringCrew
from synth_force.crews.qa_crew.qa_crew import QACrew
from synth_force.state import SynthForceState

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")


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
        tasks = json.loads(result.raw)
        self.state.tasks = tasks
        return tasks

    @listen(analyze_epic)
    def engineer_tasks(self):
        """Phase 2: For each task, create ticket, implement code, and review."""
        all_tickets = []
        repo_full_name = f"{self.state.repo_owner}/{self.state.repo_name}"

        for task in self.state.tasks:
            # Step 1: Senior SE creates a detailed ticket from the task
            ticket_result = (
                EngineeringCrew()
                .crew()
                .kickoff(
                    inputs={
                        "repo_full_name": repo_full_name,
                        "task_issue_number": task["issue_number"],
                        "ticket_issue_number": 0,  # placeholder, set after creation
                        "pr_number": 0,  # placeholder
                    }
                )
            )
            ticket_data = json.loads(ticket_result.raw)
            ticket = {
                "issue_number": ticket_data.get("issue_number", 0),
                "issue_url": ticket_data.get("issue_url", ""),
                "title": ticket_data.get("title", ""),
                "pr_url": ticket_data.get("pr_url", ""),
                "pr_number": ticket_data.get("pr_number", 0),
                "review_status": ticket_data.get("review_status", ""),
                "qa_status": "",
            }
            all_tickets.append(ticket)

        self.state.tickets = all_tickets
        return all_tickets

    @router(engineer_tasks)
    def check_reviews(self):
        """Route based on review outcomes."""
        all_approved = all(
            t.review_status == "approved" for t in self.state.tickets
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
        return "qa_ready"

    @listen("qa_ready")
    def run_qa(self):
        """Phase 3: QA tests each PR via Playwright browser testing."""
        repo_full_name = f"{self.state.repo_owner}/{self.state.repo_name}"

        for ticket in self.state.tickets:
            if not ticket.pr_number:
                continue
            qa_result = (
                QACrew()
                .crew()
                .kickoff(
                    inputs={
                        "repo_full_name": repo_full_name,
                        "pr_number": ticket.pr_number,
                        "ticket_issue_number": ticket.issue_number,
                        "test_url": f"http://localhost:3000",  # configurable
                        "qa_status": "",  # will be determined by QA
                    }
                )
            )
            result_data = json.loads(qa_result.raw)
            ticket.qa_status = result_data.get("qa_status", "unknown")

        return self.state.tickets

    @router(run_qa)
    def check_qa(self):
        """Route based on QA outcomes."""
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
        """Handle tickets that failed QA."""
        # Phase 5 will route failed tickets back to engineering.
        failed = [t for t in self.state.tickets if t.qa_status == "failed"]
        for t in failed:
            print(f"[QA FAILED] Ticket #{t.issue_number}: {t.title}")
        return "deploy_ready"

    @listen("deploy_ready")
    def deploy(self):
        """Phase 4: Create release and deploy to K8s (stubbed)."""
        repo_full_name = f"{self.state.repo_owner}/{self.state.repo_name}"
        ticket_summaries = "; ".join(
            f"#{t.issue_number} {t.title}" for t in self.state.tickets
        )

        result = (
            DevOpsCrew()
            .crew()
            .kickoff(
                inputs={
                    "repo_full_name": repo_full_name,
                    "release_tag": self.state.release_tag or "v0.1.0",
                    "release_name": f"Release {self.state.release_tag or 'v0.1.0'}",
                    "ticket_summaries": ticket_summaries,
                    "gcp_project_id": "my-gcp-project",
                    "gke_cluster_name": "synth-force-cluster",
                    "gcp_region": "us-central1",
                    "container_image": f"gcr.io/my-gcp-project/synth-force:{self.state.release_tag or 'v0.1.0'}",
                    "deployment_name": "synth-force-app",
                    "k8s_namespace": "default",
                }
            )
        )
        result_data = json.loads(result.raw)
        self.state.deployment_status = result_data.get(
            "deployment_status", "unknown"
        )
        return result_data


def run():
    """Run the flow."""
    epic_url = sys.argv[1] if len(sys.argv) > 1 else ""
    if not epic_url:
        print("Usage: synth_force <epic_issue_url>")
        print("  e.g. synth_force https://github.com/owner/repo/issues/1")
        sys.exit(1)

    # Parse owner/repo from URL
    parts = epic_url.rstrip("/").split("/")
    # Expected: https://github.com/{owner}/{repo}/issues/{number}
    owner = parts[-4]
    repo = parts[-3]

    flow = SynthForceFlow()
    flow.state.repo_owner = owner
    flow.state.repo_name = repo
    flow.state.epic_url = epic_url
    flow.kickoff()


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
