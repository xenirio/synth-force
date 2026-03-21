from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from synth_force.tools.github_tools import (
    CheckPRCIStatusTool,
    GitHubCreateBranchTool,
    GitHubCreateIssueTool,
    GitHubCreatePRTool,
    GitHubMergePRTool,
    GitHubReadFileContentTool,
    GitHubReadIssueTool,
    GitHubReadPRTool,
    GitHubReviewPRTool,
    GitWriteFileTool,
)


@CrewBase
class EngineeringCrew:
    """Crew with Senior SE and SE that creates tickets, implements code, and reviews PRs."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def senior_software_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["senior_software_engineer"],  # type: ignore[index]
            tools=[
                GitHubReadIssueTool(),
                GitHubCreateIssueTool(),
                GitHubReadPRTool(),
                GitHubReviewPRTool(),
                GitHubMergePRTool(),
                CheckPRCIStatusTool(),
            ],
            max_iter=15,
            verbose=True,
        )

    @agent
    def software_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["software_engineer"],  # type: ignore[index]
            tools=[
                GitHubReadIssueTool(),
                GitHubCreateBranchTool(),
                GitWriteFileTool(),
                GitHubCreatePRTool(),
                GitHubReadFileContentTool(),
                CheckPRCIStatusTool(),
            ],
            max_iter=15,
            verbose=True,
        )

    @agent
    def software_engineer_2(self) -> Agent:
        return Agent(
            config=self.agents_config["software_engineer_2"],  # type: ignore[index]
            tools=[
                GitHubReadIssueTool(),
                GitHubCreateBranchTool(),
                GitWriteFileTool(),
                GitHubCreatePRTool(),
                GitHubReadFileContentTool(),
                CheckPRCIStatusTool(),
            ],
            max_iter=15,
            verbose=True,
        )

    @task
    def create_ticket(self) -> Task:
        return Task(
            config=self.tasks_config["create_ticket"],  # type: ignore[index]
        )

    @task
    def implement_code(self) -> Task:
        return Task(
            config=self.tasks_config["implement_code"],  # type: ignore[index]
        )

    @task
    def review_code(self) -> Task:
        return Task(
            config=self.tasks_config["review_code"],  # type: ignore[index]
        )

    @task
    def fix_ci_failures(self) -> Task:
        return Task(
            config=self.tasks_config["fix_ci_failures"],  # type: ignore[index]
        )

    @task
    def merge_pr(self) -> Task:
        return Task(
            config=self.tasks_config["merge_pr"],  # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
