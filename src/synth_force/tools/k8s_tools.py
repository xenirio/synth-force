import time
from typing import Type

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from synth_force.tools.github_tools import _get_github


class RepoStructureInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    branch: str = Field("main", description="Branch to analyze")


class CommitWorkflowInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    workflow_filename: str = Field(
        ..., description="Workflow file name (e.g. 'ci.yml' or 'deploy.yml')"
    )
    workflow_content: str = Field(
        ..., description="Full YAML content of the GitHub Actions workflow"
    )
    branch: str = Field("main", description="Branch to commit to")
    commit_message: str = Field(
        "ci: add CI/CD workflow", description="Commit message"
    )


class GenerateWorkflowInput(BaseModel):
    platform: str = Field(
        ...,
        description=(
            "Platform: 'vercel', 'vercel-static', 'cloudrun', 'kubernetes', "
            "'ci-node' (Node.js CI on PRs), or 'ci-python' (Python CI on PRs)"
        ),
    )
    node_version: int = Field(20, description="Node.js version (default 20)")
    build_command: str = Field(
        "npm run build", description="Build command (default: npm run build)"
    )
    install_command: str = Field(
        "npm install", description="Install command (default: npm install)"
    )


WORKFLOW_TEMPLATES = {
    "ci-node": """\
name: CI
on:
  pull_request:
    branches:
      - main
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: {node_version}
      - name: Install dependencies
        run: {install_command}
      - name: Lint
        run: npm run lint --if-present
      - name: Build
        run: {build_command}
      - name: Test
        run: npm test --if-present
""",
    "ci-python": """\
name: CI
on:
  pull_request:
    branches:
      - main
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt || pip install .
          pip install ruff pytest
      - name: Lint
        run: ruff check .
      - name: Test
        run: pytest --tb=short || true
""",
    "vercel": """\
name: Deploy to Vercel
on:
  push:
    branches:
      - main
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: {node_version}
      - name: Install dependencies
        run: {install_command}
      - name: Build project
        run: {build_command}
      - name: Install Vercel CLI
        run: npm install --global vercel@latest
      - name: Pull Vercel project
        run: vercel pull --yes --environment=production --token=${{{{ secrets.VERCEL_TOKEN }}}}
        env:
          VERCEL_ORG_ID: ${{{{ secrets.VERCEL_ORG_ID }}}}
          VERCEL_PROJECT_ID: ${{{{ secrets.VERCEL_PROJECT_ID }}}}
      - name: Build with Vercel
        run: vercel build --prod --token=${{{{ secrets.VERCEL_TOKEN }}}}
        env:
          VERCEL_ORG_ID: ${{{{ secrets.VERCEL_ORG_ID }}}}
          VERCEL_PROJECT_ID: ${{{{ secrets.VERCEL_PROJECT_ID }}}}
      - name: Deploy to Vercel
        run: vercel deploy --prebuilt --prod --token=${{{{ secrets.VERCEL_TOKEN }}}}
        env:
          VERCEL_ORG_ID: ${{{{ secrets.VERCEL_ORG_ID }}}}
          VERCEL_PROJECT_ID: ${{{{ secrets.VERCEL_PROJECT_ID }}}}
""",
    "vercel-static": """\
name: Deploy to Vercel
on:
  push:
    branches:
      - main
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Install Vercel CLI
        run: npm install --global vercel@latest
      - name: Pull Vercel project
        run: vercel pull --yes --environment=production --token=${{{{ secrets.VERCEL_TOKEN }}}}
        env:
          VERCEL_ORG_ID: ${{{{ secrets.VERCEL_ORG_ID }}}}
          VERCEL_PROJECT_ID: ${{{{ secrets.VERCEL_PROJECT_ID }}}}
      - name: Build with Vercel
        run: vercel build --prod --token=${{{{ secrets.VERCEL_TOKEN }}}}
        env:
          VERCEL_ORG_ID: ${{{{ secrets.VERCEL_ORG_ID }}}}
          VERCEL_PROJECT_ID: ${{{{ secrets.VERCEL_PROJECT_ID }}}}
      - name: Deploy to Vercel
        run: vercel deploy --prebuilt --prod --token=${{{{ secrets.VERCEL_TOKEN }}}}
        env:
          VERCEL_ORG_ID: ${{{{ secrets.VERCEL_ORG_ID }}}}
          VERCEL_PROJECT_ID: ${{{{ secrets.VERCEL_PROJECT_ID }}}}
""",
    "cloudrun": """\
name: Deploy to Cloud Run
on:
  push:
    branches:
      - main
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{{{ secrets.GCP_SA_KEY }}}}
      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v2
      - name: Configure Docker
        run: gcloud auth configure-docker ${{{{ secrets.GCP_REGION }}}}-docker.pkg.dev
      - name: Build and push container
        run: |
          docker build -t ${{{{ secrets.GCP_REGION }}}}-docker.pkg.dev/${{{{ secrets.GCP_PROJECT_ID }}}}/app/main:${{{{ github.sha }}}} .
          docker push ${{{{ secrets.GCP_REGION }}}}-docker.pkg.dev/${{{{ secrets.GCP_PROJECT_ID }}}}/app/main:${{{{ github.sha }}}}
      - name: Deploy to Cloud Run
        run: |
          gcloud run deploy app \\
            --image=${{{{ secrets.GCP_REGION }}}}-docker.pkg.dev/${{{{ secrets.GCP_PROJECT_ID }}}}/app/main:${{{{ github.sha }}}} \\
            --region=${{{{ secrets.GCP_REGION }}}} \\
            --platform=managed \\
            --allow-unauthenticated
""",
    "kubernetes": """\
name: Deploy to Kubernetes
on:
  push:
    branches:
      - main
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{{{ secrets.GCP_SA_KEY }}}}
      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v2
      - name: Get GKE credentials
        uses: google-github-actions/get-gke-credentials@v2
        with:
          cluster_name: ${{{{ secrets.GKE_CLUSTER }}}}
          location: ${{{{ secrets.GCP_REGION }}}}
      - name: Build and push container
        run: |
          gcloud auth configure-docker ${{{{ secrets.GCP_REGION }}}}-docker.pkg.dev
          docker build -t ${{{{ secrets.GCP_REGION }}}}-docker.pkg.dev/${{{{ secrets.GCP_PROJECT_ID }}}}/app/main:${{{{ github.sha }}}} .
          docker push ${{{{ secrets.GCP_REGION }}}}-docker.pkg.dev/${{{{ secrets.GCP_PROJECT_ID }}}}/app/main:${{{{ github.sha }}}}
      - name: Deploy to GKE
        run: |
          kubectl set image deployment/app app=${{{{ secrets.GCP_REGION }}}}-docker.pkg.dev/${{{{ secrets.GCP_PROJECT_ID }}}}/app/main:${{{{ github.sha }}}}
          kubectl rollout status deployment/app
""",
}


class GenerateWorkflowTool(BaseTool):
    name: str = "generate_workflow"
    description: str = (
        "Generate a production-ready GitHub Actions workflow from a proven template. "
        "Available platforms: 'vercel' (Node.js app), 'vercel-static' (no package.json), "
        "'cloudrun' (Docker/API), 'kubernetes' (GKE). "
        "Returns the workflow YAML content — use commit_workflow to save it."
    )
    args_schema: Type[BaseModel] = GenerateWorkflowInput

    def _run(
        self,
        platform: str,
        node_version: int = 20,
        build_command: str = "npm run build",
        install_command: str = "npm install",
    ) -> str:
        template = WORKFLOW_TEMPLATES.get(platform)
        if not template:
            available = ", ".join(WORKFLOW_TEMPLATES.keys())
            return f"Unknown platform '{platform}'. Available: {available}"

        content = template.format(
            node_version=node_version,
            build_command=build_command,
            install_command=install_command,
        )
        return content


class AnalyzeRepoStructureTool(BaseTool):
    name: str = "analyze_repo_structure"
    description: str = (
        "Analyze a GitHub repository's file structure to determine the app type "
        "and recommend a deployment strategy. Returns file tree, detected frameworks, "
        "and deployment recommendation."
    )
    args_schema: Type[BaseModel] = RepoStructureInput

    def _run(self, repo_full_name: str, branch: str = "main") -> str:
        g = _get_github()
        repo = g.get_repo(repo_full_name)

        # Collect file tree (up to 200 files)
        files = []
        try:
            tree = repo.get_git_tree(branch, recursive=True)
            for item in tree.tree[:200]:
                files.append(item.path)
        except Exception as e:
            return f"Error reading repo tree: {e}"

        # Detect key files and frameworks
        signals = {
            "package.json": False,
            "next.config": False,
            "nuxt.config": False,
            "vite.config": False,
            "tsconfig.json": False,
            "requirements.txt": False,
            "pyproject.toml": False,
            "Dockerfile": False,
            "docker-compose": False,
            "go.mod": False,
            "Cargo.toml": False,
            "pom.xml": False,
            "index.html": False,
            "vercel.json": False,
        }

        for f in files:
            name = f.split("/")[-1]
            for key in signals:
                if key in name:
                    signals[key] = True

        # Read package.json if exists for more context
        pkg_info = ""
        if signals["package.json"]:
            try:
                content = repo.get_contents("package.json", ref=branch)
                pkg_info = content.decoded_content.decode("utf-8")[:1000]  # type: ignore[union-attr]
            except Exception:
                pass

        # Determine app type and deployment recommendation
        deploy_rec = _recommend_deployment(signals, files)

        file_tree = "\n".join(f"  {f}" for f in files[:100])
        if len(files) > 100:
            file_tree += f"\n  ... and {len(files) - 100} more files"

        detected = [k for k, v in signals.items() if v]

        result = (
            f"Repository: {repo_full_name} (branch: {branch})\n"
            f"Total files: {len(files)}\n\n"
            f"File tree:\n{file_tree}\n\n"
            f"Detected config files: {', '.join(detected) or 'none'}\n\n"
            f"Deployment recommendation:\n{deploy_rec}\n"
        )
        if pkg_info:
            result += f"\npackage.json (excerpt):\n{pkg_info}\n"

        return result


def _recommend_deployment(signals: dict, files: list[str]) -> str:
    has_docker = signals["Dockerfile"] or signals["docker-compose"]
    has_node = signals["package.json"]
    has_next = signals["next.config"]
    has_nuxt = signals["nuxt.config"]
    has_vite = signals["vite.config"]
    has_python = signals["requirements.txt"] or signals["pyproject.toml"]
    has_go = signals["go.mod"]
    has_java = signals["pom.xml"]
    has_static = signals["index.html"] and not has_node

    # Count source directories as complexity signal
    src_dirs = set()
    for f in files:
        parts = f.split("/")
        if len(parts) > 1:
            src_dirs.add(parts[0])

    multi_service = has_docker and signals["docker-compose"]

    if multi_service:
        return (
            "Type: COMPLEX_MULTI_SERVICE\n"
            "Platform: Kubernetes (GKE) or Docker Compose\n"
            "Reason: docker-compose detected — multiple services likely.\n"
            "CI/CD: GitHub Actions → build images → push to registry → deploy to K8s"
        )

    if has_next or has_nuxt:
        framework = "Next.js" if has_next else "Nuxt"
        return (
            f"Type: SSR_FRAMEWORK ({framework})\n"
            "Platform: Vercel (recommended) or Cloud Run\n"
            f"Reason: {framework} detected — Vercel has native support.\n"
            "CI/CD: GitHub Actions → Vercel auto-deploy via GitHub integration"
        )

    if has_vite or (has_node and has_static):
        return (
            "Type: STATIC_SPA\n"
            "Platform: Vercel (recommended) or Netlify\n"
            "Reason: Vite/SPA detected — static hosting is optimal.\n"
            "CI/CD: GitHub Actions → build → deploy to Vercel"
        )

    if has_node and not has_docker:
        return (
            "Type: NODE_APP\n"
            "Platform: Vercel (if frontend) or Cloud Run (if API)\n"
            "Reason: Node.js app without Docker — lightweight deployment.\n"
            "CI/CD: GitHub Actions → build & test → deploy to Vercel/Cloud Run"
        )

    if has_static:
        return (
            "Type: STATIC_SITE\n"
            "Platform: Vercel or GitHub Pages\n"
            "Reason: Pure static HTML/CSS/JS — simplest deployment.\n"
            "CI/CD: GitHub Actions → deploy to Vercel"
        )

    if has_python and not has_docker:
        return (
            "Type: PYTHON_APP\n"
            "Platform: Cloud Run (recommended) or Railway\n"
            "Reason: Python app — Cloud Run handles it well with buildpacks.\n"
            "CI/CD: GitHub Actions → build → deploy to Cloud Run"
        )

    if has_go:
        return (
            "Type: GO_APP\n"
            "Platform: Cloud Run (recommended)\n"
            "Reason: Go binary — Cloud Run is ideal for Go services.\n"
            "CI/CD: GitHub Actions → build → deploy to Cloud Run"
        )

    if has_docker and not multi_service:
        return (
            "Type: CONTAINERIZED_APP\n"
            "Platform: Cloud Run (recommended) or K8s\n"
            "Reason: Dockerfile present — containerized deployment.\n"
            "CI/CD: GitHub Actions → build image → push to registry → deploy to Cloud Run"
        )

    return (
        "Type: SIMPLE_APP\n"
        "Platform: Vercel (recommended)\n"
        "Reason: Simple project structure — Vercel handles most cases.\n"
        "CI/CD: GitHub Actions → deploy to Vercel"
    )


class CommitWorkflowTool(BaseTool):
    name: str = "commit_workflow"
    description: str = (
        "Commit a GitHub Actions workflow YAML file to .github/workflows/ "
        "in the repository. Creates or updates the workflow file."
    )
    args_schema: Type[BaseModel] = CommitWorkflowInput

    def _run(
        self,
        repo_full_name: str,
        workflow_filename: str,
        workflow_content: str,
        branch: str = "main",
        commit_message: str = "ci: add CI/CD workflow",
    ) -> str:
        import re

        # Fix common LLM mistakes with GitHub Actions expressions
        content = workflow_content
        # Fix "$ {{" or "$  {{" → "${{" (space between $ and braces)
        content = re.sub(r'\$\s+\{\{', '${{', content)
        # Fix "${{ {{ " or "{{ {{" double braces
        content = re.sub(r'\{\{\s*\{\{', '${{', content)
        # Fix "}} }}" double closing braces
        content = re.sub(r'\}\}\s*\}\}', '}}', content)
        # Fix missing $ before {{ secrets/env/github
        content = re.sub(
            r'(?<!\$)\{\{\s*(secrets|env|github|vars)\.',
            r'${{ \1.',
            content,
        )
        # Fix Vercel --prebuilt without vercel build/pull steps
        if '--prebuilt' in content and 'vercel build' not in content:
            content = content.replace('--prebuilt ', '')

        g = _get_github()
        repo = g.get_repo(repo_full_name)
        file_path = f".github/workflows/{workflow_filename}"

        try:
            existing = repo.get_contents(file_path, ref=branch)
            repo.update_file(
                file_path,
                commit_message,
                content,
                existing.sha,  # type: ignore[union-attr]
                branch=branch,
            )
            return f"Updated workflow '{file_path}' on branch '{branch}'"
        except Exception:
            repo.create_file(
                file_path, commit_message, content, branch=branch
            )
            return f"Created workflow '{file_path}' on branch '{branch}'"


class CheckWorkflowRunInput(BaseModel):
    repo_full_name: str = Field(..., description="Repository as 'owner/repo'")
    wait_seconds: int = Field(
        30,
        description="Seconds to wait for a running workflow to complete (max 120)",
    )


class CheckWorkflowRunTool(BaseTool):
    name: str = "check_workflow_run"
    description: str = (
        "Check the latest GitHub Actions workflow run status. "
        "If a run is in progress, waits up to wait_seconds for it to finish. "
        "Returns the run status, conclusion, and failure logs if any."
    )
    args_schema: Type[BaseModel] = CheckWorkflowRunInput

    def _run(self, repo_full_name: str, wait_seconds: int = 30) -> str:
        import os

        token = os.environ.get("GITHUB_TOKEN", "")
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }
        base = f"https://api.github.com/repos/{repo_full_name}/actions/runs"

        # Get latest run
        resp = requests.get(f"{base}?per_page=1", headers=headers, timeout=15)
        data = resp.json()
        runs = data.get("workflow_runs", [])
        if not runs:
            return "No workflow runs found."

        run = runs[0]
        run_id = run["id"]
        status = run["status"]
        conclusion = run.get("conclusion", "")

        # Wait if still running
        wait = min(wait_seconds, 120)
        waited = 0
        while status in ("queued", "in_progress") and waited < wait:
            time.sleep(15)
            waited += 15
            resp = requests.get(f"{base}/{run_id}", headers=headers, timeout=15)
            run = resp.json()
            status = run["status"]
            conclusion = run.get("conclusion", "")

        result = (
            f"Run #{run['run_number']}: {run['name']}\n"
            f"Status: {status} | Conclusion: {conclusion or 'pending'}\n"
            f"URL: {run['html_url']}\n"
            f"Triggered by: {run['event']} on {run.get('head_branch', '?')}\n"
        )

        # If failed, get job details and logs
        if conclusion == "failure":
            jobs_url = f"https://api.github.com/repos/{repo_full_name}/actions/runs/{run_id}/jobs"
            jobs_resp = requests.get(jobs_url, headers=headers, timeout=15)
            jobs = jobs_resp.json().get("jobs", [])
            for job in jobs:
                if job["conclusion"] == "failure":
                    result += f"\nFailed job: {job['name']}\n"
                    result += "Steps:\n"
                    for step in job.get("steps", []):
                        icon = "✅" if step["conclusion"] == "success" else "❌"
                        result += f"  {icon} {step['name']} [{step['conclusion']}]\n"

                    # Try to download job logs
                    log_url = f"https://api.github.com/repos/{repo_full_name}/actions/jobs/{job['id']}/logs"
                    try:
                        log_resp = requests.get(
                            log_url, headers=headers, timeout=30,
                            allow_redirects=True,
                        )
                        if log_resp.status_code == 200 and log_resp.text:
                            log_text = log_resp.text
                            # Find error lines
                            error_lines = [
                                line for line in log_text.split("\n")
                                if any(kw in line.lower() for kw in
                                       ["error", "failed", "fatal", "not found",
                                        "eusage", "enoent", "exit code"])
                            ]
                            if error_lines:
                                result += "\nError lines from logs:\n"
                                result += "\n".join(error_lines[:30]) + "\n"
                            else:
                                # Just show last 1500 chars
                                tail = log_text[-1500:] if len(log_text) > 1500 else log_text
                                result += f"\nLog tail:\n{tail}\n"
                    except Exception:
                        result += "\n(Could not fetch job logs)\n"

            # Also check run annotations
            annotations_url = f"https://api.github.com/repos/{repo_full_name}/check-runs/{run_id}/annotations"
            try:
                ann_resp = requests.get(annotations_url, headers=headers, timeout=10)
                if ann_resp.status_code == 200:
                    for ann in ann_resp.json()[:5]:
                        result += f"\nAnnotation: {ann.get('message', '')}\n"
            except Exception:
                pass

        return result
