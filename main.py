# MCP server: create GitHub issues.

import os
from pathlib import Path

from dotenv import load_dotenv
from github import Auth, Github
from mcp.server.mcpserver import MCPServer

# Resolve .env next to this file so the server works from any working directory
load_dotenv(Path(__file__).parent / ".env")

mcp = MCPServer("issue-function")

# Exposed to MCP hosts as `issue-function_create_issue`; the type hints become
# the JSON schema the calling LLM sees, so keep parameter names descriptive.

@mcp.tool()
def create_issue(issue_title: str, issue_text: str) -> str:
    """Create a GitHub issue in the repo named by GITHUB_REPO and return its URL."""
    token = os.getenv("ACCESS_TOKEN")
    repo_name = os.getenv("GITHUB_REPO")
    if not token or not repo_name:
        raise ValueError("ACCESS_TOKEN and GITHUB_REPO must both be set in .env")

    issue = Github(auth=Auth.Token(token)).get_repo(repo_name).create_issue(
        title=issue_title, body=issue_text
    )
    return issue.html_url


if __name__ == "__main__":
    mcp.run(transport="stdio")
