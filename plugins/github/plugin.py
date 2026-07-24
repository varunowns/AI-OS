"""
GitHub Plugin
-------------
Pulls recent commits from a GitHub repo via the REST API and writes
a summary note into the vault.

Matches the same plugin shape as career/: manifest.yaml + plugin.py
with a register(event_bus) function.

Usage:
    python main.py commits "v4run/AI-OS"
    python main.py commits "v4run/AI-OS" --out "Dev/AI-OS-commits.md"
"""

import urllib.request
import urllib.error
import json
from datetime import datetime, timezone

from config import VAULT_PATH
from core.event_bus import EventBus
from services import llm_service, obsidian_service

GITHUB_API = "https://api.github.com"

COMMITS_PROMPT = (
    "Summarize the following commits into a brief bullet-list of what "
    "changed, grouped logically. End with a one-sentence takeaway for "
    "someone who hasn't seen the repo.\n\n---\n\n{commits}"
)


def _fetch_commits(owner: str, repo: str, count: int = 10) -> list[dict]:
    """Fetch recent commits from the GitHub REST API."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/commits?per_page={count}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub API error ({exc.code}): {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach GitHub API: {exc.reason}") from exc

    commits = []
    for item in data:
        msg = item.get("commit", {}).get("message", "")
        # Use only the first line of each commit message
        first_line = msg.split("\n")[0] if msg else "(no message)"
        author = item.get("commit", {}).get("author", {}).get("name", "unknown")
        sha = item.get("sha", "")[:7]
        commits.append({"sha": sha, "message": first_line, "author": author})
    return commits


def _format_commits(commits: list[dict]) -> str:
    """Format commit list for the LLM prompt."""
    lines = []
    for c in commits:
        lines.append(f"  {c['sha']}  {c['author']}  {c['message']}")
    return "\n".join(lines)


def handle_commits(payload: dict) -> dict:
    """
    payload:
      repo: str          - "owner/repo" (default from manifest config)
      output_note: str   - where to write (optional)
      count: int         - number of commits to fetch (default 10)
    """
    repo_str = payload.get("repo", "v4run/AI-OS")
    output_note = payload.get("output_note", f"Dev/{repo_str.split('/')[-1]}-commits.md")
    count = payload.get("count", 10)

    owner, _, repo_name = repo_str.partition("/")
    if not owner or not repo_name:
        raise ValueError(f"Invalid repo format: '{repo_str}' — expected 'owner/repo'")

    commits = _fetch_commits(owner, repo_name, count)
    formatted = _format_commits(commits)
    summary = llm_service.ask(COMMITS_PROMPT.format(commits=formatted))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    content = f"# Recent Commits — {repo_str}\n\n_{now}_\n\n{summary}\n"
    obsidian_service.write_note(
        output_note, content,
        title=f"Commits: {repo_str}",
        tags=["github", "commits"],
        plugin_source="github",
    )

    return {
        "repo": repo_str,
        "output_note": str(VAULT_PATH / output_note),
        "summary": summary,
    }


def register(event_bus: EventBus, plugin_name: str = "") -> None:
    """Called once at startup to wire this plugin into the event bus."""
    event_bus.subscribe("repo.commits.summarize", handle_commits, plugin_name=plugin_name)