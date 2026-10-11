# MCP server: GitHub issue management.
#
# SDK v2. Two contract rules this file depends on:
#   1. Failures raise MCPError -> the server re-raises it unchanged as a JSON-RPC
#      error (server.py::_handle_call_tool). Anything else becomes an opaque
#      isError result, so wrapping GitHub errors is what makes them legible.
#   2. Tool parameters are read off the signature; the JSON schema the calling
#      LLM sees comes from the type hints plus any pydantic Field() bounds.

from __future__ import annotations

import itertools
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from dotenv import load_dotenv
from github import Auth, Github, GithubException
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import ToolAnnotations
from mcp_types import INTERNAL_ERROR, INVALID_PARAMS
from pydantic import Field

# Resolve .env next to this file so the server works from any working directory
load_dotenv(Path(__file__).parent / ".env")

mcp = MCPServer(
    "issue-function",
    instructions=(
        "GitHub issue management against the repo named by GITHUB_REPO: "
        "create, list, fetch, close, and label issues."
    ),
)


def _config_error(var: str) -> MCPError:
    """Missing env var is a server config fault, not a bad tool call."""
    return MCPError(
        code=INVALID_PARAMS, message=f"{var} is not set. Add it to .env."
    )


@lru_cache(maxsize=1)
def _github() -> Github:
    """Authenticated client, cached so each call reuses one connection pool."""
    token = os.getenv("ACCESS_TOKEN")
    if not token:
        raise _config_error("ACCESS_TOKEN")
    return Github(auth=Auth.Token(token))


def _repo():
    name = os.getenv("GITHUB_REPO")
    if not name:
        raise _config_error("GITHUB_REPO")
    return _github().get_repo(name)


def _api_error(exc: GithubException) -> MCPError:
    """Map a GitHub HTTP failure onto a JSON-RPC code.

    JSON-RPC reserves -32768..-32000; an HTTP status is not a legal code, so
    4xx becomes INVALID_PARAMS and everything else INTERNAL_ERROR. The original
    status rides along in `data` so the caller can still see what happened.
    """
    status = exc.status or 500
    return MCPError(
        code=INVALID_PARAMS if 400 <= status < 500 else INTERNAL_ERROR,
        message=f"GitHub API error {status}: {exc.data or exc}",
        data={"status": status, "github_message": exc.data},
    )


def _summarize(issue: Any) -> dict[str, Any]:
    """The fields every issue-returning tool shares."""
    return {
        "issue_number": issue.number,
        "title": issue.title,
        "url": issue.html_url,
        "state": issue.state,
        "labels": [l.name for l in issue.labels],
        "assignees": [a.login for a in issue.assignees],
        "created_at": issue.created_at.isoformat(),
    }


# Exposed to MCP hosts as `issue-function_create_issue`; the type hints become
# the JSON schema the calling LLM sees, so keep parameter names descriptive.
#
# Bounds go in Annotated[..., Field(...)] and never in a `= Field(...)` default:
# a Field-as-default leaves the FieldInfo object itself as the runtime value, so
# any call that skips the MCP layer (tests, the REPL) hands that object straight
# to the GitHub API. Annotated keeps the real default as the real default.


@mcp.tool(
    annotations=ToolAnnotations(
        title="Create Issue",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=True,
    )
)
def create_issue(
    issue_title: Annotated[
        str, Field(min_length=1, max_length=256, description="Issue title")
    ],
    issue_text: Annotated[
        str, Field(min_length=1, max_length=65536, description="Issue body (markdown)")
    ],
    labels: Annotated[list[str] | None, Field(description="Labels to apply")] = None,
    assignees: Annotated[
        list[str] | None, Field(description="GitHub usernames to assign")
    ] = None,
) -> dict[str, Any]:
    """
    Create an issue in the configured repository.

    Returns the issue number, URL, and state. Persistent: the issue can be
    closed but not uncreated, so repeated calls create duplicates.
    """
    try:
        issue = _repo().create_issue(
            title=issue_title,
            body=issue_text,
            labels=labels or [],
            assignees=assignees or [],
        )
        return {
            "success": True,
            "issue_number": issue.number,
            "url": issue.html_url,
            "title": issue.title,
            "state": issue.state,
            "created_at": issue.created_at.isoformat(),
        }
    except GithubException as exc:
        raise _api_error(exc) from exc


@mcp.tool(
    annotations=ToolAnnotations(
        title="List Open Issues",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
)
def list_open_issues(
    limit: Annotated[
        int, Field(ge=1, le=100, description="Max issues to return")
    ] = 10,
    labels: Annotated[list[str] | None, Field(description="Filter by labels")] = None,
    assignee: Annotated[
        str | None, Field(description="Filter by assignee username")
    ] = None,
) -> dict[str, Any]:
    """
    List open issues in the configured repository.

    Returns issue numbers, titles, labels, and URLs. Read-only. Pull requests
    are excluded: GitHub's issues endpoint returns them too.
    """
    try:
        # `not labels` and `not assignee` rather than `labels or []` / `""`:
        # PyGithub treats an empty list and an empty string as real filter
        # values, which GitHub reads as "match nothing".
        issues = _repo().get_issues(
            state="open", labels=labels or None, assignee=assignee or None
        )
        # islice stops the paginated fetch after `limit` matches instead of
        # pulling the whole open backlog over the wire.
        selected = [
            _summarize(i)
            for i in itertools.islice(
                (i for i in issues if getattr(i, "pull_request", None) is None), limit
            )
        ]
        return {"success": True, "count": len(selected), "issues": selected}
    except GithubException as exc:
        raise _api_error(exc) from exc


@mcp.tool(
    annotations=ToolAnnotations(
        title="Get Issue",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
)
def get_issue(
    issue_number: Annotated[int, Field(gt=0, description="Issue number")],
) -> dict[str, Any]:
    """
    Fetch one issue by number.

    Returns title, body, labels, assignees, state, and comment count.
    Read-only.
    """
    try:
        issue = _repo().get_issue(number=issue_number)
        return {
            "success": True,
            **_summarize(issue),
            "body": issue.body or "",
            "updated_at": issue.updated_at.isoformat(),
            "comments": issue.comments,
        }
    except GithubException as exc:
        raise _api_error(exc) from exc


@mcp.tool(
    annotations=ToolAnnotations(
        title="Close Issue",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=True,
    )
)
def close_issue(
    issue_number: Annotated[int, Field(gt=0, description="Issue number to close")],
    state_reason: Annotated[
        Literal["completed", "not_planned"], Field(description="Reason for closing")
    ] = "completed",
) -> dict[str, Any]:
    """
    Close an issue and record why.

    Idempotent: closing an already-closed issue reports success and changes
    nothing. Reversible by reopening the issue.
    """
    try:
        issue = _repo().get_issue(number=issue_number)
        if issue.state == "closed":
            return {
                "success": True,
                "issue_number": issue_number,
                "state": "closed",
                "message": f"Issue #{issue_number} was already closed",
            }
        issue.edit(state="closed", state_reason=state_reason)
        return {
            "success": True,
            "issue_number": issue_number,
            "state": "closed",
            "state_reason": state_reason,
            "url": issue.html_url,
        }
    except GithubException as exc:
        raise _api_error(exc) from exc


@mcp.tool(
    annotations=ToolAnnotations(
        title="Add Label",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=True,
    )
)
def add_label(
    issue_number: Annotated[int, Field(gt=0, description="Issue number")],
    label: Annotated[
        str, Field(min_length=1, max_length=100, description="Label to add")
    ],
) -> dict[str, Any]:
    """
    Add a label to an issue, creating it on the repo if it does not exist yet.

    Idempotent: an existing label is reported back unchanged instead of being
    written again.
    """
    try:
        issue = _repo().get_issue(number=issue_number)
        existing = {l.name for l in issue.labels}
        if label in existing:
            return {
                "success": True,
                "issue_number": issue_number,
                "labels": sorted(existing),
                "message": f"Label {label!r} already on issue #{issue_number}",
            }
        issue.add_to_labels(label)
        return {
            "success": True,
            "issue_number": issue_number,
            "label_added": label,
            "labels": sorted(existing | {label}),
        }
    except GithubException as exc:
        raise _api_error(exc) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")