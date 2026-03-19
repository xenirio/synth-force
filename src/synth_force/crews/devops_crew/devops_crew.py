from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from synth_force.tools.github_tools import GitHubCreateReleaseTool
from synth_force.tools.k8s_tools import GCloudAuthTool, KubernetesDeployTool


@CrewBase
class DevOpsCrew:
    """Crew that creates releases and deploys to K8s (stubbed)."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def devops_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["devops_engineer"],  # type: ignore[index]
            tools=[
                GitHubCreateReleaseTool(),
                GCloudAuthTool(),
                KubernetesDeployTool(),
            ],
            verbose=True,
        )

    @task
    def create_release(self) -> Task:
        return Task(
            config=self.tasks_config["create_release"],  # type: ignore[index]
        )

    @task
    def deploy(self) -> Task:
        return Task(
            config=self.tasks_config["deploy"],  # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
