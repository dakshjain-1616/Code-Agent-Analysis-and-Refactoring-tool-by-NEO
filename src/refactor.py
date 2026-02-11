import os
import logging
import re
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass
from .analysis import CodeIssue, Severity
from .git_ops import GitManager
from .runner import TestRunner, TestResult
from .llm import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class RefactoringResult:
    issue: CodeIssue
    success: bool
    applied: bool
    test_passed: bool
    commit_hash: Optional[str] = None
    error: Optional[str] = None
    original_code: Optional[str] = None
    refactored_code: Optional[str] = None


class RefactoringAgent:
    def __init__(self, config: Dict, llm_client: LLMClient, 
                 git_manager: GitManager, test_runner: TestRunner):
        self.config = config
        self.llm_client = llm_client
        self.git_manager = git_manager
        self.test_runner = test_runner
        
        self.refactor_config = config.get("refactoring", {})
        self.auto_apply = self.refactor_config.get("auto_apply", False)
        self.max_retries = self.refactor_config.get("max_retries", 3)
        self.create_backup = self.refactor_config.get("create_backup", True)
    
    def select_issues_to_refactor(self, issues: List[CodeIssue], 
                                   max_issues: int = 10) -> List[CodeIssue]:
        priority_order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]
        
        selected = []
        for severity in priority_order:
            severity_issues = [i for i in issues if i.severity == severity]
            
            refactorable_types = [
                "cyclomatic_complexity", "long_method", "large_class",
                "duplicate_code", "architectural_violation"
            ]
            refactorable = [i for i in severity_issues if i.issue_type in refactorable_types]
            
            selected.extend(refactorable[:max_issues - len(selected)])
            
            if len(selected) >= max_issues:
                break
        
        logger.info(f"Selected {len(selected)} issue(s) for refactoring")
        return selected
    
    def refactor_issue(self, issue: CodeIssue, directory: str) -> RefactoringResult:
        logger.info(f"Refactoring {issue.issue_type} in {issue.file_path}:{issue.line_start}")
        
        try:
            with open(issue.file_path, 'r', encoding='utf-8') as f:
                original_code = f.read()
        except Exception as e:
            logger.error(f"Could not read file {issue.file_path}: {e}")
            return RefactoringResult(
                issue=issue,
                success=False,
                applied=False,
                test_passed=False,
                error=f"File read error: {e}"
            )
        
        branch_name = f"{issue.issue_type}_{Path(issue.file_path).stem}_{issue.line_start}"
        branch_name = re.sub(r'[^a-zA-Z0-9_-]', '_', branch_name)
        
        if not self.git_manager.create_branch(branch_name):
            logger.error("Failed to create git branch")
            return RefactoringResult(
                issue=issue,
                success=False,
                applied=False,
                test_passed=False,
                error="Git branch creation failed"
            )
        
        refactored_code = None
        for attempt in range(self.max_retries):
            logger.info(f"Refactoring attempt {attempt + 1}/{self.max_retries}")
            
            code_section = self._extract_code_section(original_code, issue.line_start, issue.line_end)
            
            issue_desc = f"{issue.description}. {issue.suggestion or ''}"
            llm_response = self.llm_client.generate_refactoring(
                code_section, issue_desc, issue.file_path
            )
            
            if not llm_response.success:
                logger.warning(f"LLM refactoring failed: {llm_response.error}")
                continue
            
            refactored_code = self._extract_code_from_response(llm_response.content)
            
            if self.create_backup:
                backup_path = f"{issue.file_path}.backup"
                try:
                    with open(backup_path, 'w', encoding='utf-8') as f:
                        f.write(original_code)
                except Exception as e:
                    logger.warning(f"Could not create backup: {e}")
            
            try:
                new_content = self._apply_refactoring(original_code, refactored_code, 
                                                       issue.line_start, issue.line_end)
                
                with open(issue.file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                logger.info("Applied refactored code, running tests...")
                
            except Exception as e:
                logger.error(f"Failed to apply refactoring: {e}")
                continue
            
            test_result = self.test_runner.run_tests(directory)
            
            if test_result.passed:
                logger.info("Tests passed! Committing changes...")
                
                commit_msg = self.llm_client.generate_commit_message([
                    f"Fix {issue.issue_type} in {Path(issue.file_path).name}",
                    f"Line {issue.line_start}-{issue.line_end}",
                    issue.description
                ])
                
                if self.git_manager.commit_changes(commit_msg, [issue.file_path]):
                    logger.info(f"Successfully refactored and committed: {commit_msg}")
                    
                    return RefactoringResult(
                        issue=issue,
                        success=True,
                        applied=True,
                        test_passed=True,
                        commit_hash=self.git_manager.repo.head.commit.hexsha[:8],
                        original_code=code_section,
                        refactored_code=refactored_code
                    )
                else:
                    logger.error("Commit failed")
            else:
                logger.warning(f"Tests failed: {test_result.errors}")
                
                with open(issue.file_path, 'w', encoding='utf-8') as f:
                    f.write(original_code)
                
                if attempt < self.max_retries - 1:
                    logger.info("Reverting and retrying...")
                    continue
        
        logger.error("All refactoring attempts failed")
        self.git_manager.revert_changes([issue.file_path])
        
        original_branch = "main" if "main" in [h.name for h in self.git_manager.repo.heads] else "master"
        self.git_manager.checkout_branch(original_branch)
        
        return RefactoringResult(
            issue=issue,
            success=False,
            applied=False,
            test_passed=False,
            error="All refactoring attempts failed"
        )
    
    def _extract_code_section(self, code: str, line_start: int, line_end: int) -> str:
        lines = code.split('\n')
        
        start_idx = max(0, line_start - 1)
        end_idx = min(len(lines), line_end)
        
        return '\n'.join(lines[start_idx:end_idx])
    
    def _extract_code_from_response(self, response: str) -> str:
        code_block_pattern = r'```(?:python)?\n(.*?)\n```'
        matches = re.findall(code_block_pattern, response, re.DOTALL)
        
        if matches:
            return matches[0]
        
        return response.strip()
    
    def _apply_refactoring(self, original_code: str, refactored_section: str,
                          line_start: int, line_end: int) -> str:
        lines = original_code.split('\n')
        
        start_idx = max(0, line_start - 1)
        end_idx = min(len(lines), line_end)
        
        refactored_lines = refactored_section.split('\n')
        
        new_lines = lines[:start_idx] + refactored_lines + lines[end_idx:]
        
        return '\n'.join(new_lines)
    
    def run_refactoring_loop(self, issues: List[CodeIssue], directory: str,
                            max_issues: int = 10) -> List[RefactoringResult]:
        selected_issues = self.select_issues_to_refactor(issues, max_issues)
        
        results = []
        for issue in selected_issues:
            result = self.refactor_issue(issue, directory)
            results.append(result)
            
            if result.success:
                logger.info(f"✓ Successfully refactored {issue.issue_type}")
            else:
                logger.warning(f"✗ Failed to refactor {issue.issue_type}: {result.error}")
        
        return results