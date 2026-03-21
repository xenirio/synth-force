import os
import time
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


class CreateBranchInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    branch_name: str = Field(..., description="Name of the new branch")
    from_branch: str = Field("main", description="Branch to create from")


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


class ReadPRDiffInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    pr_number: int = Field(..., description="Pull request number")


class ReadFileContentInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    file_path: str = Field(..., description="Path to the file in the repo")
    branch: str = Field("main", description="Branch to read from")


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


class CheckPRCIStatusInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    pr_number: int = Field(..., description="Pull request number")
    wait_seconds: int = Field(
        120,
        description="Max seconds to wait for CI checks to complete (polls every 15s)",
    )


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


class GitHubCreateBranchTool(BaseTool):
    name: str = "github_create_branch"
    description: str = "Create a new branch in a GitHub repository from an existing branch."
    args_schema: Type[BaseModel] = CreateBranchInput

    def _run(
        self,
        repo_full_name: str,
        branch_name: str,
        from_branch: str = "main",
    ) -> str:
        g = _get_github()
        repo = g.get_repo(repo_full_name)
        source = repo.get_branch(from_branch)
        repo.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=source.commit.sha,
        )
        return f"Created branch '{branch_name}' from '{from_branch}'"


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


class GitHubReadPRDiffTool(BaseTool):
    name: str = "github_read_pr_diff"
    description: str = (
        "Read the full code diff (patches) for a pull request. "
        "Returns the actual code changes for each file."
    )
    args_schema: Type[BaseModel] = ReadPRDiffInput

    def _run(self, repo_full_name: str, pr_number: int) -> str:
        g = _get_github()
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        patches = []
        for f in pr.get_files():
            patch = f.patch or "(binary or empty)"
            patches.append(f"--- {f.filename} ---\n{patch}")
        return "\n\n".join(patches) if patches else "No file changes found."


class GitHubReadFileContentTool(BaseTool):
    name: str = "github_read_file_content"
    description: str = (
        "Read the content of a file from a GitHub repository on a specific branch."
    )
    args_schema: Type[BaseModel] = ReadFileContentInput

    def _run(
        self, repo_full_name: str, file_path: str, branch: str = "main"
    ) -> str:
        g = _get_github()
        repo = g.get_repo(repo_full_name)
        try:
            content = repo.get_contents(file_path, ref=branch)
            return content.decoded_content.decode("utf-8")  # type: ignore[union-attr]
        except Exception as e:
            return f"Error reading {file_path}: {e}"


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
        try:
            pr.create_review(body=body, event=event)
            return f"Submitted '{event}' review on PR #{pr_number}"
        except Exception as e:
            if "review on your own pull request" in str(e).lower() or "422" in str(e):
                # Self-review not allowed — post as comment instead
                comment = f"**Auto-review ({event})**: {body}" if body else f"**Auto-review ({event})**"
                pr.create_issue_comment(comment)
                return f"Self-review not allowed by GitHub. Posted review as comment on PR #{pr_number}. Review decision: {event}"
            raise


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


class CheckPRCIStatusTool(BaseTool):
    name: str = "check_pr_ci_status"
    description: str = (
        "Check CI status for a specific pull request. "
        "Polls until checks complete or timeout. Returns overall status "
        "(all_passed / failed / pending) and per-check details."
    )
    args_schema: Type[BaseModel] = CheckPRCIStatusInput

    def _run(
        self,
        repo_full_name: str,
        pr_number: int,
        wait_seconds: int = 120,
    ) -> str:
        import requests as req

        token = os.environ.get("GITHUB_TOKEN", "")
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }
        base = f"https://api.github.com/repos/{repo_full_name}"

        # Get PR head SHA
        g = _get_github()
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        head_sha = pr.head.sha

        wait = min(wait_seconds, 300)
        waited = 0

        while True:
            # Use combined status API (works with classic PATs)
            status_resp = req.get(
                f"{base}/commits/{head_sha}/status",
                headers=headers, timeout=15,
            )
            status_data = status_resp.json()
            statuses = status_data.get("statuses", [])

            # Also try check-runs API (may fail with classic PATs)
            checks = []
            try:
                checks_resp = req.get(
                    f"{base}/commits/{head_sha}/check-runs",
                    headers=headers, timeout=15,
                )
                if checks_resp.status_code == 200:
                    checks = checks_resp.json().get("check_runs", [])
            except Exception:
                pass

            has_any = len(statuses) > 0 or len(checks) > 0

            if not has_any:
                if waited >= wait:
                    return (
                        f"ci_status: pending\n"
                        f"No CI checks found for PR #{pr_number} (SHA: {head_sha[:8]}) "
                        f"after waiting {waited}s. CI may not be configured."
                    )
                time.sleep(15)
                waited += 15
                continue

            # Collect results from both APIs
            lines = [f"PR #{pr_number} CI status (SHA: {head_sha[:8]}):"]
            any_failed = False
            all_complete = True

            for s in statuses:
                state = s.get("state", "pending")
                lines.append(f"  - {s.get('context', '?')}: {state}")
                if state == "pending":
                    all_complete = False
                elif state in ("failure", "error"):
                    any_failed = True
                    desc = s.get("description", "")
                    if desc:
                        lines.append(f"    Description: {desc}")

            for cr in checks:
                status = cr.get("status", "queued")
                conclusion = cr.get("conclusion", "")
                display = conclusion or status
                lines.append(f"  - {cr.get('name', '?')}: {display}")
                if status != "completed":
                    all_complete = False
                elif conclusion and conclusion not in ("success", "skipped", "neutral"):
                    any_failed = True
                    output = cr.get("output", {})
                    if output and output.get("summary"):
                        lines.append(f"    Output: {output['summary'][:500]}")

            if all_complete or waited >= wait:
                if all_complete:
                    overall = "failed" if any_failed else "all_passed"
                else:
                    overall = "pending"
                lines.insert(1, f"ci_status: {overall}")
                return "\n".join(lines)

            time.sleep(15)
            waited += 15
