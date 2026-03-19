from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class K8sDeployInput(BaseModel):
    cluster_name: str = Field(..., description="GKE cluster name")
    namespace: str = Field("default", description="Kubernetes namespace")
    image: str = Field(..., description="Container image to deploy (e.g. 'gcr.io/project/app:v1.0.0')")
    deployment_name: str = Field(..., description="Name of the Kubernetes deployment")


class GCloudAuthInput(BaseModel):
    project_id: str = Field(..., description="GCP project ID")
    cluster_name: str = Field(..., description="GKE cluster name")
    region: str = Field("us-central1", description="GCP region")


class KubernetesDeployTool(BaseTool):
    name: str = "kubernetes_deploy"
    description: str = (
        "Deploy a container image to a Kubernetes (GKE) cluster. "
        "STUBBED: Logs deployment details without executing."
    )
    args_schema: Type[BaseModel] = K8sDeployInput

    def _run(
        self,
        cluster_name: str,
        namespace: str = "default",
        image: str = "",
        deployment_name: str = "",
    ) -> str:
        return (
            f"[STUBBED K8s Deploy]\n"
            f"Cluster: {cluster_name}\n"
            f"Namespace: {namespace}\n"
            f"Deployment: {deployment_name}\n"
            f"Image: {image}\n"
            f"Status: Deployment would be applied here. "
            f"Implement with google-cloud-container + kubernetes client."
        )


class GCloudAuthTool(BaseTool):
    name: str = "gcloud_auth"
    description: str = (
        "Authenticate to GCP and get GKE cluster credentials. "
        "STUBBED: Logs auth details without executing."
    )
    args_schema: Type[BaseModel] = GCloudAuthInput

    def _run(
        self,
        project_id: str,
        cluster_name: str,
        region: str = "us-central1",
    ) -> str:
        return (
            f"[STUBBED GCloud Auth]\n"
            f"Project: {project_id}\n"
            f"Cluster: {cluster_name}\n"
            f"Region: {region}\n"
            f"Status: Would run 'gcloud container clusters get-credentials' here. "
            f"Implement with google-cloud-container SDK."
        )
