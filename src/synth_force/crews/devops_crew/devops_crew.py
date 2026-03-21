from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from synth_force.tools.github_tools import (
    GitHubCreateReleaseTool,
    GitHubReadFileContentTool,
    GitWriteFileTool,
)
from synth_force.tools.k8s_tools import (
    AnalyzeRepoStructureTool,
    CheckWorkflowRunTool,
    CommitWorkflowTool,
    GenerateWorkflowTool,
)


@CrewBase
class DevOpsCrew:
    """Crew that analyzes repos, sets up CI/CD, monitors and fixes pipelines."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def devops_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["devops_engineer"],  # type: ignore[index]
            tools=[
                AnalyzeRepoStructureTool(),
                GenerateWorkflowTool(),
                CommitWorkflowTool(),
                CheckWorkflowRunTool(),
                GitHubCreateReleaseTool(),
                GitHubReadFileContentTool(),
                GitWriteFileTool(),
            ],
            max_iter=15,
            verbose=True,
        )

    @task
    def analyze_and_plan(self) -> Task:
        return Task(
            config=self.tasks_config["analyze_and_plan"],  # type: ignore[index]
        )

    @task
    def setup_cicd(self) -> Task:
        return Task(
            config=self.tasks_config["setup_cicd"],  # type: ignore[index]
        )

    @task
    def monitor_and_fix(self) -> Task:
        return Task(
            config=self.tasks_config["monitor_and_fix"],  # type: ignore[index]
        )

    @task
    def create_release(self) -> Task:
        return Task(
            config=self.tasks_config["create_release"],  # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
