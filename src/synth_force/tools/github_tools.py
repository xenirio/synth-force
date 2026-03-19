import os
from typing import Type

from crewai.tools import BaseTool
from github import Auth, Github
from pydantic import BaseModel, Field


def _get_github() -> Github:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN environment variable is not set")
    return Github(auth=Auth.Token(token))


# --- Input Schemas ---


class ReadIssueInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    issue_number: int = Field(..., description="Issue number to read")


class CreateIssueInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    title: str = Field(..., description="Issue title")
    body: str = Field("", description="Issue body in markdown")
    labels: list[str] = Field(default_factory=list, description="Labels to apply")


class UpdateIssueInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    issue_number: int = Field(..., description="Issue number to update")
    comment: str = Field("", description="Comment to add")
    labels: list[str] = Field(default_factory=list, description="Labels to set")
    state: str = Field("", description="State to set: 'open' or 'closed'")


class WriteFileInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    file_path: str = Field(..., description="Path of the file in the repo")
    content: str = Field(..., description="File content")
    branch: str = Field(..., description="Branch to write to")
    commit_message: str = Field(..., description="Commit message")


class CreatePRInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    title: str = Field(..., description="PR title")
    body: str = Field("", description="PR body in markdown")
    head: str = Field(..., description="Source branch")
    base: str = Field("main", description="Target branch")


class ReadPRInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    pr_number: int = Field(..., description="Pull request number")


class ReviewPRInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    pr_number: int = Field(..., description="Pull request number")
    event: str = Field(
        ..., description="Review event: 'APPROVE' or 'REQUEST_CHANGES'"
    )
    body: str = Field("", description="Review comment")


class MergePRInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    pr_number: int = Field(..., description="Pull request number")
    merge_method: str = Field("squash", description="Merge method: merge, squash, rebase")


class CreateReleaseInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    tag_name: str = Field(..., description="Tag for the release (e.g. 'v1.0.0')")
    name: str = Field(..., description="Release title")
    body: str = Field("", description="Release notes in markdown")
    target_branch: str = Field("main", description="Branch to tag from")


# --- Tools ---


class GitHubReadIssueTool(BaseTool):
    name: str = "github_read_issue"
    description: str = "Read a GitHub issue's title, body, labels, and state."
    args_schema: Type[BaseModel] = ReadIssueInput

    def _run(self, repo_full_name: str, issue_number: int) -> str:
        g = _get_github()
        repo = g.get_repo(repo_full_name)
        issue = repo.get_issue(number=issue_number)
        labels = ", ".join(l.name for l in issue.labels)
        return (
            f"Issue #{issue.number}: {issue.title}\n"
            f"State: {issue.state}\n"
            f"Labels: {labels}\n"
            f"URL: {issue.html_url}\n\n"
            f"{issue.body or '(no body)'}"
        )


class GitHubCreateIssueTool(BaseTool):
    name: str = "github_create_issue"
    description: str = "Create a new GitHub issue with title, body, and optional labels."
    args_schema: Type[BaseModel] = CreateIssueInput

    def _run(
        self,
        repo_full_name: str,
        title: str,
        body: str = "",
        labels: list[str] | None = None,
    ) -> str:
        g = _get_github()
        repo = g.get_repo(repo_full_name)
        issue = repo.create_issue(title=title, body=body, labels=labels or [])
        return (
            f"Created issue #{issue.number}: {issue.title}\n"
            f"URL: {issue.html_url}"
        )


class GitHubUpdateIssueTool(BaseTool):
    name: str = "github_update_issue"
    description: str = "Update a GitHub issue: add comment, change labels, or change state."
    args_schema: Type[BaseModel] = UpdateIssueInput

    def _run(
        self,
        repo_full_name: str,
        issue_number: int,
        comment: str = "",
        labels: list[str] | None = None,
        state: str = "",
    ) -> str:
        g = _get_github()
        repo = g.get_repo(repo_full_name)
        issue = repo.get_issue(number=issue_number)
        results = []
        if comment:
            issue.create_comment(comment)
            results.append("Comment added")
        if labels:
            issue.set_labels(*labels)
            results.append(f"Labels set to: {', '.join(labels)}")
        if state in ("open", "closed"):
            issue.edit(state=state)
            results.append(f"State set to: {state}")
        return f"Updated issue #{issue_number}: {'; '.join(results) or 'no changes'}"


class GitWriteFileTool(BaseTool):
    name: str = "git_write_file"
    description: str = (
        "Create or update a file in a GitHub repository on a specific branch. "
        "Handles both creating new files and updating existing ones."
    )
    args_schema: Type[BaseModel] = WriteFileInput

    def _run(
        self,
        repo_full_name: str,
        file_path: str,
        content: str,
        branch: str,
        commit_message: str,
    ) -> str:
        g = _get_github()
        repo = g.get_repo(repo_full_name)
        try:
            existing = repo.get_contents(file_path, ref=branch)
            repo.update_file(
                file_path,
                commit_message,
                content,
                existing.sha,  # type: ignore[union-attr]
                branch=branch,
            )
            return f"Updated file '{file_path}' on branch '{branch}'"
        except Exception:
            repo.create_file(file_path, commit_message, content, branch=branch)
            return f"Created file '{file_path}' on branch '{branch}'"


class GitHubCreatePRTool(BaseTool):
    name: str = "github_create_pr"
    description: str = "Create a pull request from a head branch to a base branch."
    args_schema: Type[BaseModel] = CreatePRInput

    def _run(
        self,
        repo_full_name: str,
        title: str,
        body: str = "",
        head: str = "",
        base: str = "main",
    ) -> str:
        g = _get_github()
        repo = g.get_repo(repo_full_name)
        pr = repo.create_pull(title=title, body=body, head=head, base=base)
        return f"Created PR #{pr.number}: {pr.title}\nURL: {pr.html_url}"


class GitHubReadPRTool(BaseTool):
    name: str = "github_read_pr"
    description: str = "Read a pull request's details including title, body, state, and diff stats."
    args_schema: Type[BaseModel] = ReadPRInput

    def _run(self, repo_full_name: str, pr_number: int) -> str:
        g = _get_github()
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        files = pr.get_files()
        file_list = "\n".join(
            f"  {f.filename} (+{f.additions} -{f.deletions})" for f in files
        )
        return (
            f"PR #{pr.number}: {pr.title}\n"
            f"State: {pr.state} | Mergeable: {pr.mergeable}\n"
            f"Head: {pr.head.ref} -> Base: {pr.base.ref}\n"
            f"URL: {pr.html_url}\n\n"
            f"Body:\n{pr.body or '(no body)'}\n\n"
            f"Changed files:\n{file_list}"
        )


class GitHubReviewPRTool(BaseTool):
    name: str = "github_review_pr"
    description: str = (
        "Submit a review on a pull request. "
        "Event must be 'APPROVE' or 'REQUEST_CHANGES'."
    )
    args_schema: Type[BaseModel] = ReviewPRInput

    def _run(
        self,
        repo_full_name: str,
        pr_number: int,
        event: str,
        body: str = "",
    ) -> str:
        g = _get_github()
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        pr.create_review(body=body, event=event)
        return f"Submitted '{event}' review on PR #{pr_number}"


class GitHubMergePRTool(BaseTool):
    name: str = "github_merge_pr"
    description: str = "Merge a pull request using the specified merge method."
    args_schema: Type[BaseModel] = MergePRInput

    def _run(
        self,
        repo_full_name: str,
        pr_number: int,
        merge_method: str = "squash",
    ) -> str:
        g = _get_github()
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        result = pr.merge(merge_method=merge_method)
        if result.merged:
            return f"PR #{pr_number} merged successfully via {merge_method}"
        return f"Failed to merge PR #{pr_number}: {result.message}"


class GitHubCreateReleaseTool(BaseTool):
    name: str = "github_create_release"
    description: str = "Create a tagged release on GitHub with release notes."
    args_schema: Type[BaseModel] = CreateReleaseInput

    def _run(
        self,
        repo_full_name: str,
        tag_name: str,
        name: str,
        body: str = "",
        target_branch: str = "main",
    ) -> str:
        g = _get_github()
        repo = g.get_repo(repo_full_name)
        release = repo.create_git_release(
            tag=tag_name,
            name=name,
            message=body,
            target_commitish=target_branch,
        )
        return (
            f"Created release '{release.title}' ({release.tag_name})\n"
            f"URL: {release.html_url}"
        )
