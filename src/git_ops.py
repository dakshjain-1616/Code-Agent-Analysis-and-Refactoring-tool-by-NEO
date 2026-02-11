import os
import logging
from typing import Optional, List, Dict
from pathlib import Path
import git
from git import Repo, GitCommandError

logger = logging.getLogger(__name__)


class GitManager:
    def __init__(self, repo_path: str, config: Dict):
        self.repo_path = repo_path
        self.config = config
        self.git_config = config.get("git", {})
        self.branch_prefix = self.git_config.get("branch_prefix", "refactor/")
        self.commit_prefix = self.git_config.get("commit_prefix", "[REFACTOR]")
        self.auto_push = self.git_config.get("auto_push", False)
        
        try:
            self.repo = Repo(repo_path)
            if self.repo.bare:
                raise ValueError("Repository is bare")
            logger.info(f"Initialized Git repository at {repo_path}")
        except git.exc.InvalidGitRepositoryError:
            logger.info(f"No git repository found at {repo_path}, initializing new repo")
            self.repo = Repo.init(repo_path)
            self._initial_commit()
    
    def _initial_commit(self):
        try:
            self.repo.index.add(['*'])
            self.repo.index.commit("Initial commit")
            logger.info("Created initial commit")
        except Exception as e:
            logger.warning(f"Could not create initial commit: {e}")
    
    def get_current_branch(self) -> str:
        try:
            return self.repo.active_branch.name
        except Exception:
            return "HEAD"
    
    def create_branch(self, branch_name: str) -> bool:
        try:
            full_branch_name = f"{self.branch_prefix}{branch_name}"
            
            if full_branch_name in self.repo.heads:
                logger.warning(f"Branch {full_branch_name} already exists")
                self.repo.git.checkout(full_branch_name)
                return True
            
            current = self.repo.active_branch
            new_branch = self.repo.create_head(full_branch_name)
            new_branch.checkout()
            
            logger.info(f"Created and checked out branch: {full_branch_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create branch {branch_name}: {e}")
            return False
    
    def stage_files(self, file_paths: List[str]) -> bool:
        try:
            for file_path in file_paths:
                self.repo.index.add([file_path])
            logger.info(f"Staged {len(file_paths)} file(s)")
            return True
        except Exception as e:
            logger.error(f"Failed to stage files: {e}")
            return False
    
    def commit_changes(self, message: str, files: Optional[List[str]] = None) -> bool:
        try:
            if files:
                self.stage_files(files)
            
            if not self.repo.index.diff("HEAD"):
                logger.warning("No changes to commit")
                return True
            
            full_message = f"{self.commit_prefix} {message}" if not message.startswith(self.commit_prefix) else message
            commit = self.repo.index.commit(full_message)
            
            logger.info(f"Committed changes: {commit.hexsha[:8]} - {full_message}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to commit changes: {e}")
            return False
    
    def push_changes(self, remote: str = "origin", branch: Optional[str] = None) -> bool:
        try:
            if not self.auto_push:
                logger.info("Auto-push disabled, skipping push")
                return True
            
            branch = branch or self.get_current_branch()
            
            if remote not in [r.name for r in self.repo.remotes]:
                logger.warning(f"Remote '{remote}' not found, skipping push")
                return True
            
            self.repo.git.push(remote, branch)
            logger.info(f"Pushed changes to {remote}/{branch}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to push changes: {e}")
            return False
    
    def revert_changes(self, file_paths: Optional[List[str]] = None) -> bool:
        try:
            if file_paths:
                self.repo.index.checkout(file_paths, force=True)
                logger.info(f"Reverted {len(file_paths)} file(s)")
            else:
                self.repo.head.reset(index=True, working_tree=True)
                logger.info("Reverted all changes")
            return True
            
        except Exception as e:
            logger.error(f"Failed to revert changes: {e}")
            return False
    
    def checkout_branch(self, branch_name: str) -> bool:
        try:
            self.repo.git.checkout(branch_name)
            logger.info(f"Checked out branch: {branch_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to checkout branch {branch_name}: {e}")
            return False
    
    def get_diff_summary(self, file_path: Optional[str] = None) -> str:
        try:
            if file_path:
                diff = self.repo.git.diff('HEAD', file_path)
            else:
                diff = self.repo.git.diff('HEAD')
            return diff
        except Exception as e:
            logger.error(f"Failed to get diff: {e}")
            return ""
    
    def has_uncommitted_changes(self) -> bool:
        return self.repo.is_dirty(untracked_files=True)