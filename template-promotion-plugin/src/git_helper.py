"""Git operations wrapper for template promotion workflow.

Uses subprocess for Git commands (branch, commit, push) and Harness Code API for PR creation.
No additional dependencies required beyond requests (already in requirements.txt).
"""

import logging
from pathlib import Path
from typing import List, Optional
import subprocess

logger = logging.getLogger(__name__)


class GitOperations:
    """Handle Git operations for promotion workflow."""

    def __init__(self, repo_path: str = "."):
        """Initialize with repository path."""
        self.repo_path = Path(repo_path)

    def create_branch(self, branch_name: str) -> str:
        """Create and checkout new branch.

        Args:
            branch_name: Branch name (e.g., promotion/template-v2-to-tier-1)

        Returns:
            Branch name
        """
        try:
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.repo_path,
                check=True,
                capture_output=True
            )
            logger.info(f"  ✓ Created branch: {branch_name}")
            return branch_name
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create branch: {e.stderr.decode()}")
            raise

    def commit_files(self, files: List[str], message: str) -> str:
        """Stage and commit files.

        Args:
            files: List of file paths to commit
            message: Commit message

        Returns:
            Commit SHA
        """
        try:
            # Stage files
            subprocess.run(
                ["git", "add"] + files,
                cwd=self.repo_path,
                check=True
            )

            # Commit
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.repo_path,
                check=True,
                capture_output=True
            )

            # Get commit SHA
            sha_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                check=True,
                capture_output=True
            )
            sha = sha_result.stdout.decode().strip()

            logger.info(f"  ✓ Committed: {sha[:8]}")
            return sha
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to commit: {e.stderr.decode()}")
            raise

    def push_branch(
        self,
        branch_name: str,
        api_key: Optional[str] = None,
        username: str = "git"
    ) -> None:
        """Push branch to remote.

        Args:
            branch_name: Branch name to push
            api_key: Optional Harness API key for authentication
            username: Username for git auth (default: "git")
        """
        try:
            # If API key provided, inject it into remote URL for authentication
            if api_key:
                # Modify remote URL to include credentials (works for Harness Code)
                # Get current remote URL
                get_remote = subprocess.run(
                    ["git", "remote", "get-url", "origin"],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True
                )

                if get_remote.returncode == 0:
                    remote_url = get_remote.stdout.strip()

                    # If HTTPS URL, inject credentials
                    if remote_url.startswith("https://"):
                        # Convert https://app.harness.io/... to https://git:api_key@app.harness.io/...
                        auth_url = remote_url.replace("https://", f"https://{username}:{api_key}@")

                        # Temporarily set remote URL with credentials
                        subprocess.run(
                            ["git", "remote", "set-url", "origin", auth_url],
                            cwd=self.repo_path,
                            check=True,
                            capture_output=True
                        )

                        # Push
                        subprocess.run(
                            ["git", "push", "-u", "origin", branch_name],
                            cwd=self.repo_path,
                            check=True,
                            capture_output=True
                        )

                        # Restore original remote URL (remove credentials)
                        subprocess.run(
                            ["git", "remote", "set-url", "origin", remote_url],
                            cwd=self.repo_path,
                            check=True,
                            capture_output=True
                        )

                        logger.info(f"  ✓ Pushed branch: {branch_name} (using API key auth)")
                        return

            # Fall back to standard push (uses existing git credentials)
            subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                cwd=self.repo_path,
                check=True,
                capture_output=True
            )
            logger.info(f"  ✓ Pushed branch: {branch_name}")

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"Failed to push: {error_msg}")

            # Make push failure non-fatal
            logger.warning("  ⚠️ Push failed, but continuing with promotion")
            logger.info("  ℹ️  To fix: Configure git credentials or ensure remote is accessible")
            logger.info("  ℹ️  You can manually push with: git push -u origin " + branch_name)

    def create_pull_request(
        self,
        title: str,
        body: str,
        source_branch: str,
        target_branch: str,
        api_key: str,
        account_id: str,
        org_id: str,
        project_id: str,
        repo_id: str
    ) -> Optional[str]:
        """Create pull request using Harness Code API.

        Args:
            title: PR title
            body: PR description
            source_branch: Source branch name
            target_branch: Target branch name
            api_key: Harness API key
            account_id: Harness account ID
            org_id: Harness organization ID
            project_id: Harness project ID
            repo_id: Harness Code repository ID

        Returns:
            PR URL or None if failed
        """
        import requests

        repo_ref = f"{account_id}/{org_id}/{project_id}/{repo_id}"
        url = f"https://app.harness.io/gateway/code/api/v1/repos/{repo_ref}/pullreq"

        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json"
        }

        payload = {
            "title": title,
            "description": body,
            "source_branch": source_branch,
            "target_branch": target_branch
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            pr_number = response.json().get('number')
            pr_url = f"https://app.harness.io/ng/account/{account_id}/module/code/orgs/{org_id}/projects/{project_id}/repos/{repo_id}/pull-requests/{pr_number}"
            logger.info(f"  ✓ Created PR #{pr_number}: {pr_url}")
            return pr_url
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to create PR: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Failed to create PR: {str(e)}")
            return None
