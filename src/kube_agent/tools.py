"""Tool definitions for LLM function calling.

OpenAI 형식의 도구(tool) 정의와 실행 디스패처를 제공합니다.
모든 Kubernetes 및 Gitea 작업을 LLM이 호출할 수 있는 함수로 노출합니다.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from kube_agent.file_ops import FileOps
from kube_agent.gitea_ops import GiteaOps
from kube_agent.kubernetes_ops import KubernetesOps

logger = logging.getLogger(__name__)


# OpenAI function calling 형식의 도구 정의 목록
TOOLS: list[dict[str, Any]] = [
    # ---- Kubernetes 도구 ----
    {
        "type": "function",
        "function": {
            "name": "k8s_list_pods",
            "description": "List all pods in the current namespace with status, restarts, and age.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "k8s_get_pod",
            "description": "Get detailed information about a specific pod.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the pod to inspect.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "k8s_get_pod_logs",
            "description": "Get logs from a specific pod. Optionally specify container and tail lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the pod.",
                    },
                    "container": {
                        "type": "string",
                        "description": "Container name (optional, uses default if not specified).",
                    },
                    "tail": {
                        "type": "integer",
                        "description": "Number of last lines to return (default: 100).",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "k8s_list_deployments",
            "description": "List all deployments in the current namespace with ready/total replicas and age.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "k8s_get_deployment",
            "description": "Get detailed information about a specific deployment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the deployment.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "k8s_restart_deployment",
            "description": "Perform a rolling restart of a deployment (equivalent to kubectl rollout restart).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the deployment to restart.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "k8s_scale_deployment",
            "description": "Scale a deployment to a specified number of replicas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the deployment to scale.",
                    },
                    "replicas": {
                        "type": "integer",
                        "description": "Target number of replicas.",
                    },
                },
                "required": ["name", "replicas"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "k8s_list_services",
            "description": "List all services in the current namespace with type, cluster IP, and ports.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "k8s_list_configmaps",
            "description": "List all configmaps in the current namespace.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "k8s_get_configmap",
            "description": "Get the data content of a specific configmap.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the configmap.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "k8s_list_secrets",
            "description": "List all secrets in the current namespace (names and types only, no secret data shown).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "k8s_get_events",
            "description": "Get recent events in the current namespace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of events to return (default: 20).",
                    },
                },
                "required": [],
            },
        },
    },
    # ---- Gitea 도구 ----
    {
        "type": "function",
        "function": {
            "name": "gitea_list_repos",
            "description": "List all accessible Gitea repositories.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitea_get_repo",
            "description": "Get detailed information about a specific Gitea repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner username.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Repository name.",
                    },
                },
                "required": ["owner", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitea_create_repo",
            "description": "Create a new Gitea repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Repository name.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Repository description.",
                    },
                    "private": {
                        "type": "boolean",
                        "description": "Whether the repo should be private (default: true).",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitea_delete_repo",
            "description": "Delete a Gitea repository. This is irreversible.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner username.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Repository name.",
                    },
                },
                "required": ["owner", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitea_list_branches",
            "description": "List branches of a Gitea repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner username.",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name.",
                    },
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitea_list_users",
            "description": "List Gitea users (admin only).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitea_create_webhook",
            "description": "Create a webhook on a Gitea repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner username.",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name.",
                    },
                    "target_url": {
                        "type": "string",
                        "description": "The URL the webhook should POST to.",
                    },
                    "events": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of events to trigger the webhook (default: ['push']).",
                    },
                },
                "required": ["owner", "repo", "target_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitea_list_webhooks",
            "description": "List webhooks of a Gitea repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner username.",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name.",
                    },
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitea_clone_repo",
            "description": "Clone a Git repository to a local path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_url": {
                        "type": "string",
                        "description": "The URL of the repository to clone.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Local path to clone into.",
                    },
                },
                "required": ["repo_url", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitea_git_pull",
            "description": "Pull latest changes in a local Git repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the local Git repository.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitea_git_status",
            "description": "Show the working tree status of a local Git repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the local Git repository.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitea_commit_and_push",
            "description": "Add all changes, commit with a message, and push to remote.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the local Git repository.",
                    },
                    "message": {
                        "type": "string",
                        "description": "Commit message.",
                    },
                },
                "required": ["path", "message"],
            },
        },
    },
    # ---- 파일시스템 도구 ----
    {
        "type": "function",
        "function": {
            "name": "file_list",
            "description": "List files and directories at the given path. Use after cloning a repo to explore its structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list.",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "If true, list all files recursively (default: false).",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read the contents of a file. Use to inspect configuration files, Helm values, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to read.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "Write content to a file (overwrites existing). Use to modify Helm values, configs, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to write.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content to write.",
                    },
                    "create_dirs": {
                        "type": "boolean",
                        "description": "If true, create parent directories if they don't exist (default: false).",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
]


async def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    k8s: KubernetesOps,
    gitea: GiteaOps,
    files: FileOps,
) -> str:
    """도구 이름에 따라 적절한 메서드를 실행합니다.

    Args:
        tool_name: 실행할 도구 이름 (예: k8s_list_pods, gitea_list_repos, file_read)
        arguments: 도구에 전달할 인자 딕셔너리
        k8s: Kubernetes 작업 인스턴스
        gitea: Gitea 작업 인스턴스
        files: 파일시스템 작업 인스턴스

    Returns:
        도구 실행 결과 문자열
    """
    try:
        # Kubernetes 도구 디스패치
        if tool_name == "k8s_list_pods":
            return k8s.list_pods()
        elif tool_name == "k8s_get_pod":
            return k8s.get_pod(name=arguments["name"])
        elif tool_name == "k8s_get_pod_logs":
            return k8s.get_pod_logs(
                name=arguments["name"],
                container=arguments.get("container"),
                tail=arguments.get("tail", 100),
            )
        elif tool_name == "k8s_list_deployments":
            return k8s.list_deployments()
        elif tool_name == "k8s_get_deployment":
            return k8s.get_deployment(name=arguments["name"])
        elif tool_name == "k8s_restart_deployment":
            return k8s.restart_deployment(name=arguments["name"])
        elif tool_name == "k8s_scale_deployment":
            return k8s.scale_deployment(name=arguments["name"], replicas=arguments["replicas"])
        elif tool_name == "k8s_list_services":
            return k8s.list_services()
        elif tool_name == "k8s_list_configmaps":
            return k8s.list_configmaps()
        elif tool_name == "k8s_get_configmap":
            return k8s.get_configmap(name=arguments["name"])
        elif tool_name == "k8s_list_secrets":
            return k8s.list_secrets()
        elif tool_name == "k8s_get_events":
            return k8s.get_events(limit=arguments.get("limit", 20))

        # Gitea 도구 디스패치
        elif tool_name == "gitea_list_repos":
            return await gitea.list_repos()
        elif tool_name == "gitea_get_repo":
            return await gitea.get_repo(owner=arguments["owner"], name=arguments["name"])
        elif tool_name == "gitea_create_repo":
            return await gitea.create_repo(
                name=arguments["name"],
                description=arguments.get("description", ""),
                private=arguments.get("private", True),
            )
        elif tool_name == "gitea_delete_repo":
            return await gitea.delete_repo(owner=arguments["owner"], name=arguments["name"])
        elif tool_name == "gitea_list_branches":
            return await gitea.list_branches(owner=arguments["owner"], repo=arguments["repo"])
        elif tool_name == "gitea_list_users":
            return await gitea.list_users()
        elif tool_name == "gitea_create_webhook":
            return await gitea.create_webhook(
                owner=arguments["owner"],
                repo=arguments["repo"],
                target_url=arguments["target_url"],
                events=arguments.get("events"),
            )
        elif tool_name == "gitea_list_webhooks":
            return await gitea.list_webhooks(owner=arguments["owner"], repo=arguments["repo"])
        elif tool_name == "gitea_clone_repo":
            return await gitea.git_clone(repo_url=arguments["repo_url"], path=arguments["path"])
        elif tool_name == "gitea_git_pull":
            return await gitea.git_pull(path=arguments["path"])
        elif tool_name == "gitea_git_status":
            return await gitea.git_status(path=arguments["path"])
        elif tool_name == "gitea_commit_and_push":
            return await gitea.git_commit_and_push(path=arguments["path"], message=arguments["message"])

        # 파일시스템 도구 디스패치
        elif tool_name == "file_list":
            return files.list_directory(path=arguments["path"], recursive=arguments.get("recursive", False))
        elif tool_name == "file_read":
            return files.read_file(path=arguments["path"])
        elif tool_name == "file_write":
            return files.write_file(
                path=arguments["path"],
                content=arguments["content"],
                create_dirs=arguments.get("create_dirs", False),
            )
        else:
            return f"알 수 없는 도구: {tool_name}"

    except KeyError as exc:
        return f"도구 '{tool_name}' 실행 시 필수 인자 누락: {exc}"
    except json.JSONDecodeError as exc:
        return f"도구 '{tool_name}' 인자 파싱 오류: {exc}"
    except Exception as exc:
        logger.error("도구 '%s' 실행 중 예외: %s", tool_name, exc)
        return f"도구 '{tool_name}' 실행 중 오류: {exc}"
