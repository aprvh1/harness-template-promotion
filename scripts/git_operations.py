#!/usr/bin/env python3
"""Git operations for template promotion workflow.

This module provides functions for Git operations including branch creation,
commits, and pull request creation for the GitOps workflow.
"""

import os
import sys
import subprocess
from typing import List, Optional, Dict
from pathlib import Path


class GitOperations:
    """Handle Git operations for template promotion."""

    def __init__(self, repo_path: Optional[str] = None):
        """
        Initialize Git operations.

        Args:
            repo_path: Path to git repository (defaults to current directory)
        """
        self.repo_path = Path(repo_path or os.getcwd())

        # Verify this is a git repository
        if not (self.repo_path / '.git').exists():
            raise ValueError(f"{self.repo_path} is not a git repository")

    def run_command(self, cmd: List[str], check=True) -> subprocess.CompletedProcess:
        """
        Run a git command.

        Args:
            cmd: Command and arguments as list
            check: Raise exception on non-zero exit code

        Returns:
            CompletedProcess instance
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=check
            )
            return result
        except subprocess.CalledProcessError as e:
            print(f"Command failed: {' '.join(cmd)}", file=sys.stderr)
            print(f"stdout: {e.stdout}", file=sys.stderr)
            print(f"stderr: {e.stderr}", file=sys.stderr)
            raise

    def get_current_branch(self) -> str:
        """Get the current branch name."""
        result = self.run_command(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
        return result.stdout.strip()

    def get_git_user(self) -> Dict[str, str]:
        """Get configured git user name and email."""
        try:
            name_result = self.run_command(['git', 'config', 'user.name'])
            email_result = self.run_command(['git', 'config', 'user.email'])
            return {
                'name': name_result.stdout.strip(),
                'email': email_result.stdout.strip()
            }
        except subprocess.CalledProcessError:
            return {'name': 'Claude Code', 'email': 'noreply@anthropic.com'}

    def create_branch(self, branch_name: str, from_branch: Optional[str] = None) -> str:
        """
        Create a new git branch.

        Args:
            branch_name: Name of the new branch
            from_branch: Base branch (defaults to current branch)

        Returns:
            Created branch name
        """
        if from_branch:
            # Ensure we're on the from_branch
            self.run_command(['git', 'checkout', from_branch])

        # Create and checkout new branch
        self.run_command(['git', 'checkout', '-b', branch_name])

        print(f"✓ Created branch: {branch_name}")
        return branch_name

    def stage_files(self, file_paths: List[str]) -> None:
        """
        Stage files for commit.

        Args:
            file_paths: List of file paths to stage
        """
        for file_path in file_paths:
            self.run_command(['git', 'add', file_path])

        print(f"✓ Staged {len(file_paths)} file(s)")

    def commit_files(self, files: List[str], message: str, co_author: Optional[str] = None) -> str:
        """
        Stage and commit files.

        Args:
            files: List of file paths to commit
            message: Commit message
            co_author: Optional co-author string (e.g., "Name <email>")

        Returns:
            Commit SHA
        """
        # Stage files
        self.stage_files(files)

        # Build commit message with co-author
        commit_msg = message
        if co_author:
            commit_msg = f"{message}\n\nCo-Authored-By: {co_author}"

        # Commit
        self.run_command(['git', 'commit', '-m', commit_msg])

        # Get commit SHA
        result = self.run_command(['git', 'rev-parse', 'HEAD'])
        commit_sha = result.stdout.strip()

        print(f"✓ Committed: {commit_sha[:8]}")
        return commit_sha

    def push_branch(self, branch_name: Optional[str] = None, force: bool = False) -> None:
        """
        Push branch to remote.

        Args:
            branch_name: Branch to push (defaults to current branch)
            force: Use force push
        """
        if not branch_name:
            branch_name = self.get_current_branch()

        cmd = ['git', 'push', '-u', 'origin', branch_name]
        if force:
            cmd.insert(2, '--force')

        self.run_command(cmd)
        print(f"✓ Pushed branch: {branch_name}")

    def create_pull_request(self, title: str, body: str, base: str = 'main', head: Optional[str] = None) -> Optional[str]:
        """
        Create a pull request using GitHub CLI (gh).

        Args:
            title: PR title
            body: PR description
            base: Base branch (default: main)
            head: Head branch (defaults to current branch)

        Returns:
            PR URL if successful, None otherwise
        """
        if not head:
            head = self.get_current_branch()

        try:
            # Check if gh CLI is available
            subprocess.run(['gh', '--version'], capture_output=True, check=True)

            # Create PR
            result = self.run_command([
                'gh', 'pr', 'create',
                '--title', title,
                '--body', body,
                '--base', base,
                '--head', head
            ])

            pr_url = result.stdout.strip()
            print(f"✓ Created PR: {pr_url}")
            return pr_url

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Warning: Could not create PR automatically: {e}", file=sys.stderr)
            print(f"Please create PR manually for branch: {head} → {base}", file=sys.stderr)
            return None

    def get_file_status(self) -> Dict[str, List[str]]:
        """
        Get git status of files.

        Returns:
            Dictionary with 'modified', 'added', 'deleted', 'untracked' lists
        """
        result = self.run_command(['git', 'status', '--porcelain'])
        lines = result.stdout.strip().split('\n')

        status = {
            'modified': [],
            'added': [],
            'deleted': [],
            'untracked': []
        }

        for line in lines:
            if not line:
                continue

            state = line[:2]
            filepath = line[3:]

            if state == '??':
                status['untracked'].append(filepath)
            elif 'M' in state:
                status['modified'].append(filepath)
            elif 'A' in state:
                status['added'].append(filepath)
            elif 'D' in state:
                status['deleted'].append(filepath)

        return status

    def has_changes(self) -> bool:
        """Check if there are any uncommitted changes."""
        result = self.run_command(['git', 'status', '--porcelain'])
        return bool(result.stdout.strip())

    def get_diff(self, file_path: Optional[str] = None) -> str:
        """
        Get git diff for file(s).

        Args:
            file_path: Specific file to diff (None for all changes)

        Returns:
            Diff output
        """
        cmd = ['git', 'diff']
        if file_path:
            cmd.append(file_path)

        result = self.run_command(cmd)
        return result.stdout


def main():
    """Test git operations."""
    import argparse

    parser = argparse.ArgumentParser(description='Test git operations')
    parser.add_argument('--test-branch', action='store_true', help='Test branch creation')
    parser.add_argument('--test-commit', action='store_true', help='Test commit')
    parser.add_argument('--test-pr', action='store_true', help='Test PR creation')

    args = parser.parse_args()

    try:
        git_ops = GitOperations()

        print(f"Current branch: {git_ops.get_current_branch()}")
        print(f"Git user: {git_ops.get_git_user()}")

        if args.test_branch:
            print("\nTesting branch creation...")
            test_branch = f"test-branch-{os.getpid()}"
            git_ops.create_branch(test_branch)
            print(f"Created branch: {test_branch}")

        if git_ops.has_changes():
            print("\nUncommitted changes:")
            status = git_ops.get_file_status()
            for category, files in status.items():
                if files:
                    print(f"  {category}: {', '.join(files)}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
