"""Fixtures for the MCP server tests.

Issues are SimpleNamespace rather than MagicMock on purpose: MagicMock invents
an attribute for every name, so `getattr(issue, "pull_request", None)` would
always look truthy and every fixture issue would be silently classified as a
pull request. Explicit is the only correct option here.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def env(monkeypatch):
    """Valid config for every test; individual tests delete what they need."""
    monkeypatch.setenv("ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("GITHUB_REPO", "testowner/testrepo")


@pytest.fixture(autouse=True)
def repo():
    """Patch the PyGithub entry point and clear the cached client.

    main._github is lru_cached, so without the cache_clear every test would
    reuse the client built from a previous test's environment.
    """
    with patch("main.Github") as gh_class:
        client = MagicMock()
        gh_class.return_value = client
        repo_obj = MagicMock()
        client.get_repo.return_value = repo_obj

        import main

        main._github.cache_clear()
        yield repo_obj
        main._github.cache_clear()


def make_issue(
    number: int = 42,
    *,
    state: str = "open",
    labels: tuple[str, ...] = ("bug", "enhancement"),
    assignees: tuple[str, ...] = ("alice",),
    pull_request: bool = False,
) -> SimpleNamespace:
    """A stand-in for github.Issue.Issue."""
    stamp = SimpleNamespace(isoformat=lambda: "2026-01-15T10:30:00+00:00")
    return SimpleNamespace(
        number=number,
        title=f"Issue {number}",
        html_url=f"https://github.com/testowner/testrepo/issues/{number}",
        body="Body text",
        state=state,
        labels=[SimpleNamespace(name=n) for n in labels],
        assignees=[SimpleNamespace(login=a) for a in assignees],
        created_at=stamp,
        updated_at=stamp,
        comments=0,
        pull_request={"url": "..."} if pull_request else None,
        add_to_labels=MagicMock(),
        edit=MagicMock(),
    )


@pytest.fixture
def issue():
    return make_issue()


@pytest.fixture
def issues():
    """Five issues: even numbers open, odd numbers carry a pull_request."""
    return [make_issue(n, pull_request=bool(n % 2)) for n in range(1, 6)]