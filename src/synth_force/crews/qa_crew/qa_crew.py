from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from synth_force.tools.github_tools import (
    GitHubReadFileContentTool,
    GitHubReadIssueTool,
    GitHubReadPRDiffTool,
    GitHubReadPRTool,
    GitHubUpdateIssueTool,
)


@CrewBase
class QACrew:
    """Crew that reviews PR code against ticket requirements and updates ticket status."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def qa_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["qa_engineer"],  # type: ignore[index]
            tools=[
                GitHubReadIssueTool(),
                GitHubReadPRTool(),
                GitHubReadPRDiffTool(),
                GitHubReadFileContentTool(),
                GitHubUpdateIssueTool(),
            ],
            max_iter=10,
            verbose=True,
        )

    @task
    def test_pr(self) -> Task:
        return Task(
            config=self.tasks_config["test_pr"],  # type: ignore[index]
        )

    @task
    def update_ticket_status(self) -> Task:
        return Task(
            config=self.tasks_config["update_ticket_status"],  # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
