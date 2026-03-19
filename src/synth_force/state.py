from pydantic import BaseModel


class EpicTask(BaseModel):
    issue_number: int
    issue_url: str
    title: str


class Ticket(BaseModel):
    issue_number: int
    issue_url: str
    title: str
    pr_url: str = ""
    pr_number: int = 0
    review_status: str = ""  # approved | changes_requested
    qa_status: str = ""  # passed | failed


class SynthForceState(BaseModel):
    repo_owner: str = ""
    repo_name: str = ""
    epic_url: str = ""
    tasks: list[EpicTask] = []
    tickets: list[Ticket] = []
    release_tag: str = ""
    deployment_status: str = ""
