# GitHub Commits Fetcher

A Python package for fetching and processing GitHub commits.

## Installation

```
pip install github-commits-fetcher
```

## Usage

```python
from github_commits_fetcher import GitHubCommitsFetcher

fetcher = GitHubCommitsFetcher(
    repo_owner='owner',
    repo_name='repo',
    github_token='your_token'
)

fetcher.process_commits()
```

For command-line usage:

```
github-commits-fetcher --repo_owner owner --repo_name repo --github_token your_token
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
