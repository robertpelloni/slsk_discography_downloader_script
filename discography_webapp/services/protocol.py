import os
import subprocess
import re
from typing import List, Dict


class ProtocolService:
    def __init__(self, logger):
        self.logger = logger
        self.root_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def _run_git(self, args: List[str], cwd=None) -> str:
        if cwd is None:
            cwd = self.root_dir
        try:
            result = subprocess.run(
                ["git"] + args, cwd=cwd, capture_output=True,
                text=True, check=True, timeout=30
            )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            raise Exception(f"Git command timed out: git {' '.join(args)}")
        except subprocess.CalledProcessError as e:
            self.logger.error(
                f"Git command failed: git {' '.join(args)}\nError: {e.stderr}")
            raise Exception(f"Git error: {e.stderr}")

    async def sync_repository(self):
        """Step 1: Upstream Tracking & Submodule Sanitization."""
        self.logger.info("Starting Repository Synchronization...")
        self.logger.info("Fetching all remotes and tags...")
        self._run_git(["fetch", "--all", "--tags"])
        self.logger.info("Merging origin/main...")
        self._run_git(["merge", "origin/main", "-m",
                       "AI Protocol: Auto-sync with origin/main"])
        self.logger.info("Updating submodules recursively...")
        self._run_git(["submodule", "update", "--init", "--recursive"])
        self.logger.info("Repository synchronized successfully.")

    async def reconcile_branches(self):
        """Step 2: Dual-Direction Intelligent Merge Engine."""
        self.logger.info("Starting Branch Reconciliation...")
        if os.path.exists(os.path.join(self.root_dir, ".git", "MERGE_HEAD")):
            self.logger.warning(
                "A merge is already in progress. Aborting reconciliation.")
            return

        branches_raw = self._run_git(["branch"]).split("\n")
        current_branch = ""
        feature_branches = []
        for b in branches_raw:
            b = b.strip()
            if b.startswith("* "):
                current_branch = b[2:]
            elif b and b != "main":
                feature_branches.append(b)

        self.logger.info(f"Current branch: {current_branch}")
        self.logger.info(f"Feature branches: {feature_branches}")

        if current_branch == "main":
            for fb in feature_branches:
                try:
                    self.logger.info(
                        f"Attempting forward merge of {fb} into main...")
                    self._run_git(["merge", fb, "-m",
                                   f"AI Protocol: Forward merge {fb}"])
                except Exception as e:
                    self.logger.warning(
                        f"Forward merge of {fb} failed: {e}")
                    self._run_git(["merge", "--abort"])

        for fb in feature_branches:
            try:
                self.logger.info(
                    f"Attempting reverse merge of main into {fb}...")
                self._run_git(["checkout", fb])
                self._run_git(["merge", "main", "-m",
                               f"AI Protocol: Reverse merge main into {fb}"])
                self._run_git(["checkout", current_branch])
            except Exception as e:
                self.logger.warning(f"Reverse merge into {fb} failed: {e}")
                self._run_git(["checkout", current_branch])

        self.logger.info("Branch reconciliation complete.")

    async def extract_roadmap(self):
        """Step 3: Workspace Cleanup & Roadmap Extraction.

        Scans source code for TODO comments.  Does NOT overwrite TODO.md.
        """
        self.logger.info("Extracting Roadmap and TODOs...")
        try:
            result = subprocess.run(
                ["grep", "-rI",
                 "--exclude-dir=data", "--exclude-dir=__pycache__",
                 "--exclude-dir=.git", "--exclude-dir=venv",
                 "--exclude=*.pyc", "--exclude=*.pyd",
                 "TODO", os.path.join(self.root_dir, "discography_webapp")],
                capture_output=True, text=True, timeout=10
            )
            todos = [t for t in result.stdout.split("\n") if t.strip()]
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            todos = []

        self.logger.info(
            f"Roadmap extraction complete. Found {len(todos)} TODO comments.")
