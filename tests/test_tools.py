"""Tests for the five MCP tools.

Two call styles are used on purpose:
  * direct `main.<tool>(...)` for behaviour, against a mocked repo;
  * `mcp.call_tool(...)` for anything the MCP layer owns - argument validation
    and error classification. The decorators do NOT put `.annotations` on the
    function objects and do NOT validate Field() bounds on a direct call, so
    those two things are only observable through the server.
"""

from __future__ import annotations

import asyncio

import pytest
from github import GithubException

import main
from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared.exceptions import MCPError
from mcp_types import INTERNAL_ERROR, INVALID_PARAMS
from tests.conftest import make_issue


def call(name: str, arguments: dict):
    """Invoke a tool through the MCP layer (validation + error handling)."""
    return asyncio.run(main.mcp.call_tool(name, arguments))


def tools() -> dict:
    return {t.name: t for t in asyncio.run(main.mcp.list_tools())}


# --------------------------------------------------------------------------
# create_issue
# --------------------------------------------------------------------------


class TestCreateIssue:
    def test_returns_issue_fields(self, repo, issue):
        repo.create_issue.return_value = issue

        result = main.create_issue(issue_title="Bug", issue_text="Steps to repro")

        assert result["success"] is True
        assert result["issue_number"] == 42
        assert result["state"] == "open"
        assert result["url"].endswith("/issues/42")

    def test_forwards_labels_and_assignees(self, repo, issue):
        repo.create_issue.return_value = issue

        main.create_issue(
            issue_title="Bug",
            issue_text="Body",
            labels=["bug", "urgent"],
            assignees=["alice"],
        )

        repo.create_issue.assert_called_once_with(
            title="Bug", body="Body", labels=["bug", "urgent"], assignees=["alice"]
        )

    def test_omitted_optionals_become_empty_lists(self, repo, issue):
        repo.create_issue.return_value = issue

        main.create_issue(issue_title="Bug", issue_text="Body")

        repo.create_issue.assert_called_once_with(
            title="Bug", body="Body", labels=[], assignees=[]
        )

    @pytest.mark.parametrize("missing", ["ACCESS_TOKEN", "GITHUB_REPO"])
    def test_missing_config_raises(self, monkeypatch, missing):
        monkeypatch.delenv(missing)

        with pytest.raises(MCPError) as exc:
            main.create_issue(issue_title="Bug", issue_text="Body")

        assert exc.value.code == INVALID_PARAMS
        assert missing in exc.value.message

    def test_api_error_is_wrapped(self, repo):
        repo.create_issue.side_effect = GithubException(
            422, {"message": "Validation Failed"}
        )

        with pytest.raises(MCPError) as exc:
            main.create_issue(issue_title="Bug", issue_text="Body")

        assert exc.value.code == INVALID_PARAMS
        assert exc.value.data["status"] == 422
        assert "Validation Failed" in exc.value.message


# --------------------------------------------------------------------------
# list_open_issues
# --------------------------------------------------------------------------


class TestListOpenIssues:
    def test_returns_requested_issues(self, repo, issues):
        repo.get_issues.return_value = issues

        result = main.list_open_issues(limit=2)

        assert result["count"] == 2
        assert [i["issue_number"] for i in result["issues"]] == [2, 4]

    def test_excludes_pull_requests(self, repo, issues):
        """GitHub's issues endpoint mixes in PRs; they must not be returned."""
        repo.get_issues.return_value = issues

        result = main.list_open_issues(limit=100)

        assert all(i["issue_number"] % 2 == 0 for i in result["issues"])

    def test_forwards_filters_without_emptying_them(self, repo, issues):
        repo.get_issues.return_value = issues

        main.list_open_issues(limit=10, labels=["bug"], assignee="alice")

        # An empty list or "" is a real filter value to PyGithub: it would ask
        # GitHub for issues matching nothing.
        repo.get_issues.assert_called_once_with(
            state="open", labels=["bug"], assignee="alice"
        )

    def test_no_filters_sends_none(self, repo, issues):
        repo.get_issues.return_value = issues

        main.list_open_issues()

        repo.get_issues.assert_called_once_with(
            state="open", labels=None, assignee=None
        )

    def test_empty_repo(self, repo):
        repo.get_issues.return_value = []

        assert main.list_open_issues() == {"success": True, "count": 0, "issues": []}


# --------------------------------------------------------------------------
# get_issue
# --------------------------------------------------------------------------


class TestGetIssue:
    def test_returns_full_issue(self, repo, issue):
        repo.get_issue.return_value = issue

        result = main.get_issue(issue_number=42)

        assert result["body"] == "Body text"
        assert result["labels"] == ["bug", "enhancement"]
        assert result["assignees"] == ["alice"]
        assert result["comments"] == 0

    def test_missing_body_becomes_empty_string(self, repo, issue):
        issue.body = None
        repo.get_issue.return_value = issue

        assert main.get_issue(issue_number=42)["body"] == ""

    def test_not_found_is_a_client_error(self, repo):
        repo.get_issue.side_effect = GithubException(404, {"message": "Not Found"})

        with pytest.raises(MCPError) as exc:
            main.get_issue(issue_number=999)

        assert exc.value.code == INVALID_PARAMS
        assert exc.value.data["status"] == 404


# --------------------------------------------------------------------------
# close_issue
# --------------------------------------------------------------------------


class TestCloseIssue:
    def test_closes_open_issue(self, repo, issue):
        repo.get_issue.return_value = issue

        result = main.close_issue(issue_number=42, state_reason="not_planned")

        assert result["state"] == "closed"
        assert result["state_reason"] == "not_planned"
        issue.edit.assert_called_once_with(state="closed", state_reason="not_planned")

    def test_defaults_to_completed(self, repo, issue):
        repo.get_issue.return_value = issue

        main.close_issue(issue_number=42)

        issue.edit.assert_called_once_with(state="closed", state_reason="completed")

    def test_idempotent_on_closed_issue(self, repo, issue):
        issue.state = "closed"
        repo.get_issue.return_value = issue

        result = main.close_issue(issue_number=42)

        assert result["success"] is True
        assert "already closed" in result["message"]
        issue.edit.assert_not_called()


# --------------------------------------------------------------------------
# add_label
# --------------------------------------------------------------------------


class TestAddLabel:
    def test_adds_missing_label(self, repo, issue):
        repo.get_issue.return_value = issue

        result = main.add_label(issue_number=42, label="priority")

        assert result["label_added"] == "priority"
        assert result["labels"] == ["bug", "enhancement", "priority"]
        issue.add_to_labels.assert_called_once_with("priority")

    def test_idempotent_on_existing_label(self, repo, issue):
        repo.get_issue.return_value = issue

        result = main.add_label(issue_number=42, label="bug")

        assert "already on issue" in result["message"]
        assert result["labels"] == ["bug", "enhancement"]
        issue.add_to_labels.assert_not_called()


# --------------------------------------------------------------------------
# Schema, annotations, and the error contract as the MCP layer sees them
# --------------------------------------------------------------------------


class TestPublishedSchema:
    def test_all_five_tools_are_registered(self):
        assert set(tools()) == {
            "create_issue",
            "list_open_issues",
            "get_issue",
            "close_issue",
            "add_label",
        }

    @pytest.mark.parametrize(
        ("name", "read_only", "destructive", "idempotent"),
        [
            ("create_issue", False, True, False),
            ("list_open_issues", True, False, True),
            ("get_issue", True, False, True),
            ("close_issue", False, True, True),
            ("add_label", False, True, True),
        ],
    )
    def test_annotations_match_behaviour(
        self, name, read_only, destructive, idempotent
    ):
        ann = tools()[name].annotations

        assert ann.read_only_hint is read_only
        assert ann.destructive_hint is destructive
        assert ann.idempotent_hint is idempotent
        assert ann.open_world_hint is True
        assert ann.title

    def test_required_and_bounded_parameters_reach_the_schema(self):
        schema = tools()["list_open_issues"].input_schema

        # Every parameter is optional here, so pydantic omits "required" entirely.
        assert schema.get("required", []) == []
        assert schema["properties"]["limit"]["maximum"] == 100
        assert schema["properties"]["limit"]["default"] == 10
        assert tools()["get_issue"].input_schema["required"] == ["issue_number"]
        assert tools()["add_label"].input_schema["properties"]["label"]["minLength"] == 1
        reasons = tools()["close_issue"].input_schema["properties"]["state_reason"]
        assert reasons["enum"] == ["completed", "not_planned"]


class TestValidation:
    """Field() bounds are enforced by the server, not by a direct call.

    MCPServer.call_tool raises ToolError for rejected arguments; the request
    handler is what turns that into an is_error result for the client. What
    matters here is that the rejection happens *before* the tool body runs.
    """

    @pytest.mark.parametrize(
        ("name", "args"),
        [
            ("get_issue", {"issue_number": 0}),
            ("add_label", {"issue_number": 1, "label": ""}),
            ("create_issue", {"issue_title": "", "issue_text": "body"}),
            ("close_issue", {"issue_number": 1, "state_reason": "because"}),
            ("list_open_issues", {"limit": 0}),
        ],
    )
    def test_bad_arguments_never_reach_the_body(self, repo, name, args):
        with pytest.raises(ToolError):
            call(name, args)

        repo.get_issue.assert_not_called()
        repo.create_issue.assert_not_called()
        repo.get_issues.assert_not_called()

    def test_valid_arguments_reach_the_body(self, repo):
        repo.get_issue.return_value = make_issue()

        result = call("get_issue", {"issue_number": 42})

        assert result.is_error is not True
        repo.get_issue.assert_called_once_with(number=42)


class TestErrorContract:
    def test_mcp_error_reaches_the_caller_as_a_protocol_error(self, repo):
        repo.get_issue.side_effect = GithubException(500, {"message": "boom"})

        with pytest.raises(MCPError) as exc:
            call("get_issue", {"issue_number": 42})

        # 5xx is a server fault, so it must not masquerade as a bad request.
        assert exc.value.code == INTERNAL_ERROR
        assert exc.value.data["status"] == 500

    def test_github_4xx_is_a_client_error(self, repo):
        repo.get_issue.side_effect = GithubException(404, {"message": "Not Found"})

        with pytest.raises(MCPError) as exc:
            call("get_issue", {"issue_number": 999})

        assert exc.value.code == INVALID_PARAMS