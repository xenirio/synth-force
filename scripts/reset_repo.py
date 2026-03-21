#!/usr/bin/env python
"""Reset a GitHub repository to a clean state.

Closes all issues, closes all PRs, deletes all branches except main,
and force-pushes main to a single commit with only README.md.

Usage: uv run python scripts/reset_repo.py <owner/repo>
"""
import os
import sys

from github import Auth, Github, GithubException


def reset_repo(repo_full_name: str):
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("Error: GITHUB_TOKEN not set")
        sys.exit(1)

    g = Github(auth=Auth.Token(token))
    repo = g.get_repo(repo_full_name)

    # 1. Close all open issues (non-PR)
    open_issues = list(repo.get_issues(state="open"))
    issue_count = 0
    for issue in open_issues:
        if issue.pull_request:
            continue
        issue.edit(state="closed")
        issue_count += 1
        print(f"  Closed issue #{issue.number}: {issue.title}")
    print(f"Closed {issue_count} issues")

    # 2. Close all open PRs
    open_prs = list(repo.get_pulls(state="open"))
    for pr in open_prs:
        pr.edit(state="closed")
        print(f"  Closed PR #{pr.number}: {pr.title}")
    print(f"Closed {len(open_prs)} PRs")

    # 3. Delete all branches except main/master
    default_branch = repo.default_branch
    branches = list(repo.get_branches())
    deleted = 0
    for branch in branches:
        if branch.name == default_branch:
            continue
        try:
            repo.get_git_ref(f"heads/{branch.name}").delete()
            print(f"  Deleted branch: {branch.name}")
            deleted += 1
        except GithubException as e:
            print(f"  Failed to delete {branch.name}: {e}")
    print(f"Deleted {deleted} branches")

    # 4. Force-push main to a single commit with only README.md
    print("Resetting main to single commit with README.md...")

    # Create a new tree with just README.md
    readme_content = f"# {repo.name}\n"
    blob = repo.create_git_blob(readme_content, "utf-8")
    from github import InputGitTreeElement

    tree = repo.create_git_tree(
        [InputGitTreeElement(path="README.md", mode="100644", type="blob", sha=blob.sha)]
    )

    # Create an initial commit (no parents = root commit)
    commit = repo.create_git_commit(
        message="Initial commit",
        tree=tree,
        parents=[],
    )

    # Force-update main ref
    ref = repo.get_git_ref(f"heads/{default_branch}")
    ref.edit(sha=commit.sha, force=True)
    print(f"Force-pushed {default_branch} to {commit.sha[:8]}")

    # 5. Delete all releases and tags
    releases = list(repo.get_releases())
    for release in releases:
        release.delete_release()
        print(f"  Deleted release: {release.tag_name}")
    print(f"Deleted {len(releases)} releases")

    tags = list(repo.get_tags())
    for tag in tags:
        try:
            repo.get_git_ref(f"tags/{tag.name}").delete()
            print(f"  Deleted tag: {tag.name}")
        except GithubException:
            pass
    print(f"Deleted {len(tags)} tags")

    print(f"\nDone! {repo_full_name} is now clean.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/reset_repo.py <owner/repo>")
        sys.exit(1)

    repo_name = sys.argv[1]
    print(f"This will RESET {repo_name}:")
    print("  - Close all issues and PRs")
    print("  - Delete all branches except main")
    print("  - Force-push main to a single README.md commit")
    print("  - Delete all releases and tags")
    print()
    confirm = input("Type 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        sys.exit(0)

    reset_repo(repo_name)
