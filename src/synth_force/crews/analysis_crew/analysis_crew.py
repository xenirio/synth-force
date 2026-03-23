from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from synth_force.model_config import get_model
from synth_force.tools.github_tools import GitHubCreateIssueTool, GitHubReadIssueTool


@CrewBase
class AnalysisCrew:
    """Crew that analyzes an epic and breaks it into task issues."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def system_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["system_analyst"],  # type: ignore[index]
            tools=[GitHubReadIssueTool(), GitHubCreateIssueTool()],
            llm=get_model("ANALYST"),
            max_iter=15,
            verbose=True,
        )

    @task
    def analyze_epic(self) -> Task:
        return Task(
            config=self.tasks_config["analyze_epic"],  # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
