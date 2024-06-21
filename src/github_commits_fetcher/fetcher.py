import os
import json
import requests
import time
import logging
import argparse
import pandas as pd
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

try:
    load_dotenv()
except Exception as e:
    logger.warning(f"Failed to load .env file: {e}")


class GitHubCommitsFetcher:

    def __init__(
        self,
        repo_owner,
        repo_name,
        per_page=100,
        commit_hash_end=None,
        save_files=False,
        github_token=None,
    ):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.per_page = per_page
        self.commit_hash_end = commit_hash_end
        self.save_files = save_files
        self.commits_url = (
            f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/commits"
        )

        # Use provided token, or fall back to environment variable
        self.github_token = github_token or os.getenv("GITHUB_ACCESS_TOKEN")
        if not self.github_token:
            raise ValueError(
                "GitHub access token not provided and not found in environment variables."
            )

        self.headers = {"Authorization": f"token {self.github_token}"}
        self.commits_info = []
        self.commit_content_dir = f"{self.repo_owner}_{self.repo_name}_commit_contents"
        self.progress_file = f"{self.repo_owner}_{self.repo_name}_progress.json"
        self.session = self._create_session()
        self.load_progress()

    def _create_session(self):
        session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=20)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def load_progress(self):
        if os.path.exists(self.progress_file):
            with open(self.progress_file, "r") as f:
                progress_data = json.load(f)
                self.commits_info = progress_data.get("commits_info", [])
                self.processed_commits = set(progress_data.get("processed_commits", []))
        else:
            self.processed_commits = set()

    def save_progress(self):
        with open(self.progress_file, "w") as f:
            json.dump(
                {
                    "commits_info": self.commits_info,
                    "processed_commits": list(self.processed_commits),
                },
                f,
            )

    def handle_rate_limit(self, response):
        if response.status_code == 403 and "X-RateLimit-Remaining" in response.headers:
            remaining = int(response.headers["X-RateLimit-Remaining"])
            if remaining == 0:
                reset_time = int(response.headers["X-RateLimit-Reset"])
                sleep_time = reset_time - time.time()
                if sleep_time > 0:
                    logger.error(
                        f"Rate limit exceeded. Waiting for {sleep_time:.2f} seconds..."
                    )
                    time.sleep(sleep_time)
                return True
        return False

    def fetch_commits(self, page):
        params = {"per_page": self.per_page, "page": page}
        while True:
            try:
                response = self.session.get(
                    self.commits_url, headers=self.headers, params=params
                )
                if self.handle_rate_limit(response):
                    continue
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching commits: {e}")
                if (
                    isinstance(e, requests.exceptions.HTTPError)
                    and e.response.status_code == 403
                ):
                    continue
                return None

    def fetch_commit_details(self, commit):
        commit_detail_url = commit["url"]
        while True:
            try:
                response = self.session.get(commit_detail_url, headers=self.headers)
                if self.handle_rate_limit(response):
                    continue
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching commit details: {e}")
                if (
                    isinstance(e, requests.exceptions.HTTPError)
                    and e.response.status_code == 403
                ):
                    continue
                return None

    def save_commit_files(self, commit_hash, commit_detail_data):
        commit_dir = os.path.join(
            self.commit_content_dir,
            f"{self.repo_owner}_{self.repo_name}_{len(self.commits_info)+1}-{commit_hash}",
        )
        os.makedirs(commit_dir, exist_ok=True)
        for file in commit_detail_data["files"]:
            filename = file["filename"]
            patch = file.get("patch", "")
            file_path = os.path.join(commit_dir, filename.replace("/", "_"))
            with open(file_path, "w") as f:
                f.write(patch)
        commit_info_path = os.path.join(commit_dir, "commit_info.json")
        with open(commit_info_path, "w") as f:
            json.dump(commit_detail_data, f, indent=4)

    def process_commit(self, commit):
        commit_hash = commit["sha"]
        if commit_hash in self.processed_commits:
            logger.info(f"Commit {commit_hash} already processed. Skipping...")
            return None
        commit_url = commit["html_url"]
        author_name = commit["commit"]["author"]["name"]
        author_url = (
            f"https://github.com/{commit['author']['login']}"
            if commit["author"]
            else "N/A"
        )
        commit_date = commit["commit"]["author"]["date"]
        commit_message = commit["commit"]["message"]

        commit_detail_data = self.fetch_commit_details(commit)
        if commit_detail_data and self.save_files:
            self.save_commit_files(commit_hash, commit_detail_data)

        commit_info = {
            "Commit URL": commit_url,
            "Author Name": author_name,
            "Author URL": author_url,
            "Commit Date": commit_date,
            "Commit Message": commit_message,
        }
        return commit_info

    def process_commits(self):
        logger.info(
            f"Starting to process commits from {self.repo_owner}/{self.repo_name}"
        )
        page = 1
        all_commits_fetched = False

        while not all_commits_fetched:
            commits_data = self.fetch_commits(page)
            if not commits_data:
                break

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [
                    executor.submit(self.process_commit, commit)
                    for commit in commits_data
                ]
                for future in as_completed(futures):
                    commit_info = future.result()
                    if commit_info:
                        self.commits_info.append(commit_info)
                        commit_hash = commit_info["Commit URL"].split("/")[-1]
                        self.processed_commits.add(commit_hash)
                        logger.info(f"Processed commit {commit_hash}")

            if self.commit_hash_end and any(
                commit["sha"] == self.commit_hash_end for commit in commits_data
            ):
                all_commits_fetched = True

            page += 1
            self.save_progress()

            time.sleep(6)

        logger.info("Finished processing all commits.")

    def convert_progress_to_excel(self, excel_file):
        if not os.path.exists(self.progress_file):
            logger.error(f"Progress file {self.progress_file} does not exist.")
            return

        with open(self.progress_file, "r") as f:
            progress_data = json.load(f)

        df = pd.DataFrame(progress_data["commits_info"])
        df.to_excel(excel_file, index=False)
        logger.info(f"Progress data has been successfully saved to {excel_file}")


def main():
    parser = argparse.ArgumentParser(description="Fetch and process GitHub commits.")
    parser.add_argument(
        "--repo_owner", type=str, required=True, help="GitHub repository owner"
    )
    parser.add_argument(
        "--repo_name", type=str, required=True, help="GitHub repository name"
    )
    parser.add_argument(
        "--per_page", type=int, default=100, help="Number of commits per page"
    )
    parser.add_argument("--commit_hash_end", type=str, help="Commit hash to stop at")
    parser.add_argument(
        "--save_files", action="store_true", help="Option to save commit files"
    )
    parser.add_argument(
        "--convert_to_excel",
        action="store_true",
        help="Option to convert progress file to Excel",
    )
    parser.add_argument("--github_token", type=str, help="GitHub access token")
    args = parser.parse_args()

    fetcher = GitHubCommitsFetcher(
        repo_owner=args.repo_owner,
        repo_name=args.repo_name,
        per_page=args.per_page,
        commit_hash_end=args.commit_hash_end,
        save_files=args.save_files,
        github_token=args.github_token,
    )

    fetcher.process_commits()

    if args.convert_to_excel:
        excel_file = f"{args.repo_owner}_{args.repo_name}_progress.xlsx"
        fetcher.convert_progress_to_excel(excel_file)


if __name__ == "__main__":
    main()
