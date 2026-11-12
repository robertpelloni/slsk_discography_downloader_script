import os
import subprocess
from typing import List


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

        # Check available remotes
        remotes_raw = self._run_git(["remote"])
        remotes = [r.strip() for r in remotes_raw.split('\n') if r.strip()]

        for remote in ['upstream', 'origin']:
            if remote in remotes:
                self.logger.info(f"Merging {remote}/main...")
                try:
                    self._run_git(["merge", f"{remote}/main", "-m",
                                   f"AI Protocol: Auto-sync with {remote}/main"])
                    self.logger.info(f"Successfully merged {remote}/main")
                except Exception as e:
                    self.logger.warning(f"Failed to merge {remote}/main: {e}")
                    self._run_git(["merge", "--abort"])

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

        Scans source code for TODO comments using pure Python (cross-platform)
        and preserves existing manual TODO.md sections when updating.
        """
        self.logger.info("Extracting Roadmap and TODOs...")
        todos = []
        target_dir = os.path.join(self.root_dir, "discography_webapp")
        exclude_dirs = {"data", "__pycache__", ".git", "venv", "downloads", "delete_review", "target", ".pi", ".pi-lens", ".ruff_cache"}
        exclude_extensions = {".pyc", ".pyd", ".db", ".log", ".exe", ".dll"}

        try:
            for root, dirs, files in os.walk(target_dir):
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                for file in files:
                    if any(file.endswith(ext) for ext in exclude_extensions):
                        continue
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            for line_num, line in enumerate(f, 1):
                                if "TODO" in line:
                                    relative_path = os.path.relpath(file_path, self.root_dir)
                                    todos.append(f"{relative_path}:{line_num}: {line.strip()}")
                    except Exception:
                        pass
        except Exception as e:
            self.logger.error(f"Error extracting roadmap: {e}")

        self.logger.info(
            f"Roadmap extraction complete. Found {len(todos)} TODO comments."
        )

        # Write or merge into TODO.md without clobbering manual sections
        if todos:
            todo_path = os.path.join(self.root_dir, "TODO.md")
            section_header = "## Extracted Source TODOs"
            extracted_block = "\n".join(f"- {t}" for t in todos) + "\n"
            try:
                if os.path.exists(todo_path):
                    with open(todo_path, "r", encoding="utf-8") as f:
                        existing = f.read()
                    if section_header in existing:
                        prefix = existing.split(section_header, 1)[0].rstrip()
                        updated = f"{prefix}\n\n{section_header}\n\n{extracted_block}"
                    else:
                        updated = f"{existing.rstrip()}\n\n{section_header}\n\n{extracted_block}"
                    with open(todo_path, "w", encoding="utf-8") as f:
                        f.write(updated)
                else:
                    with open(todo_path, "w", encoding="utf-8") as f:
                        f.write("# TODOs\n")
                        for t in todos:
                            f.write(f"- {t}\n")
            except OSError as e:
                self.logger.warning(f"Could not write to TODO.md: {e}")
