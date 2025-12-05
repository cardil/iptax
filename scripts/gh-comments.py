#!/usr/bin/env python
"""Fetch unresolved review comments from a GitHub PR.

Based on: https://stackoverflow.com/a/66072198/844449

Usage:
    python scripts/gh-comments.py [PR_NUMBER]
    python scripts/gh-comments.py 17
"""

import json
import subprocess
import sys


def get_pr_number() -> int:
    """Get PR number from argument or current branch."""
    if len(sys.argv) > 1:
        return int(sys.argv[1])

    # Try to get from current branch
    result = subprocess.run(
        ["gh", "pr", "view", "--json", "number", "--jq", ".number"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return int(result.stdout.strip())

    print("Usage: python scripts/gh-comments.py <PR_NUMBER>", file=sys.stderr)
    sys.exit(1)


def get_repo_info() -> tuple[str, str]:
    """Get owner and repo from current directory."""
    result = subprocess.run(
        [
            "gh",
            "repo",
            "view",
            "--json",
            "owner,name",
            "--jq",
            "[.owner.login, .name] | @tsv",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Error: Could not determine repository", file=sys.stderr)
        sys.exit(1)

    parts = result.stdout.strip().split("\t")
    return parts[0], parts[1]


def fetch_unresolved_comments(owner: str, repo: str, pr_number: int) -> list[dict]:
    """Fetch unresolved review threads from a PR using GraphQL."""
    query = """
    query($owner: String!, $repo: String!, $pr: Int!, $cursor: String) {
        repository(owner: $owner, name: $repo) {
            pullRequest(number: $pr) {
                reviewThreads(first: 100, after: $cursor) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    nodes {
                        isResolved
                        isOutdated
                        path
                        line
                        comments(first: 10) {
                            nodes {
                                author {
                                    login
                                }
                                body
                                createdAt
                                url
                            }
                        }
                    }
                }
            }
        }
    }
    """

    variables = {
        "owner": owner,
        "repo": repo,
        "pr": pr_number,
        "cursor": None,
    }

    all_threads = []
    has_next_page = True

    while has_next_page:
        result = subprocess.run(
            [
                "gh",
                "api",
                "graphql",
                "-f",
                f"query={query}",
                "-f",
                f"owner={owner}",
                "-f",
                f"repo={repo}",
                "-F",
                f"pr={pr_number}",
                "-f",
                f"cursor={variables['cursor'] or ''}",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"Error: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        data = json.loads(result.stdout)
        threads_data = data["data"]["repository"]["pullRequest"]["reviewThreads"]

        for thread in threads_data["nodes"]:
            if not thread["isResolved"]:
                all_threads.append(thread)

        has_next_page = threads_data["pageInfo"]["hasNextPage"]
        variables["cursor"] = threads_data["pageInfo"]["endCursor"]

    return all_threads


def print_threads(threads: list[dict]) -> None:
    """Print unresolved threads in a readable format."""
    if not threads:
        print("✅ No unresolved review comments!")
        return

    print(f"📋 Found {len(threads)} unresolved review thread(s):\n")

    for i, thread in enumerate(threads, 1):
        path = thread["path"]
        line = thread.get("line", "?")
        outdated = " (outdated)" if thread["isOutdated"] else ""

        print(f"── Thread {i}: {path}:{line}{outdated} ──")

        for comment in thread["comments"]["nodes"]:
            author = comment["author"]["login"] if comment["author"] else "unknown"
            body = comment["body"]
            url = comment["url"]

            print(f"  @{author}:")
            # Print full body with indentation
            for line_text in body.split("\n"):
                print(f"    {line_text}")
            print(f"  🔗 {url}")
            print()


def main() -> None:
    """Main entry point."""
    pr_number = get_pr_number()
    owner, repo = get_repo_info()

    print(f"Fetching unresolved comments for {owner}/{repo}#{pr_number}...")
    threads = fetch_unresolved_comments(owner, repo, pr_number)
    print_threads(threads)


if __name__ == "__main__":
    main()
