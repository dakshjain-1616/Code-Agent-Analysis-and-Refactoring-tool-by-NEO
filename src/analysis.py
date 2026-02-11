import ast
import os
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import subprocess
from radon.complexity import cc_visit
from radon.metrics import mi_visit
import pylint.lint
from io import StringIO
import sys

logger = logging.getLogger(__name__)


class Severity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class CodeIssue:
    file_path: str
    line_start: int
    line_end: int
    issue_type: str
    severity: Severity
    description: str
    suggestion: Optional[str] = None
    metric_value: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "issue_type": self.issue_type,
            "severity": self.severity.value,
            "description": self.description,
            "suggestion": self.suggestion,
            "metric_value": self.metric_value
        }


class CodeAnalyzer:
    def __init__(self, config: Dict[str, Any], llm_client=None):
        self.config = config
        self.llm_client = llm_client
        self.analysis_config = config.get("analysis", {})
        self.complexity_threshold = self.analysis_config.get("complexity_threshold", 10)
        self.max_method_lines = self.analysis_config.get("max_method_lines", 50)
        self.max_class_lines = self.analysis_config.get("max_class_lines", 300)
        
    def analyze_file(self, file_path: str) -> List[CodeIssue]:
        issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            if not code.strip():
                return issues
            
            issues.extend(self._analyze_complexity(file_path, code))
            issues.extend(self._analyze_with_pylint(file_path))
            issues.extend(self._analyze_structure(file_path, code))
            
            if self.llm_client:
                issues.extend(self._analyze_with_llm(file_path, code))
                
        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            
        return issues
    
    def _analyze_complexity(self, file_path: str, code: str) -> List[CodeIssue]:
        issues = []
        
        try:
            complexity_results = cc_visit(code)
            
            for result in complexity_results:
                if result.complexity >= self.complexity_threshold:
                    severity = Severity.CRITICAL if result.complexity >= 20 else \
                              Severity.HIGH if result.complexity >= 15 else Severity.MEDIUM
                    
                    issues.append(CodeIssue(
                        file_path=file_path,
                        line_start=result.lineno,
                        line_end=result.endline if hasattr(result, 'endline') else result.lineno,
                        issue_type="cyclomatic_complexity",
                        severity=severity,
                        description=f"High cyclomatic complexity ({result.complexity}) in {result.name}",
                        suggestion="Consider breaking down into smaller functions",
                        metric_value=result.complexity
                    ))
        except Exception as e:
            logger.warning(f"Complexity analysis failed for {file_path}: {e}")
            
        return issues
    
    def _analyze_with_pylint(self, file_path: str) -> List[CodeIssue]:
        issues = []
        
        try:
            pylint_output = StringIO()
            sys.stdout = pylint_output
            sys.stderr = StringIO()
            
            try:
                pylint.lint.Run([
                    file_path,
                    '--output-format=json',
                    '--disable=all',
                    '--enable=unused-variable,unused-import,unreachable,duplicate-code'
                ], exit=False)
            except SystemExit:
                pass
            finally:
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
            
            output = pylint_output.getvalue()
            if output:
                try:
                    pylint_results = json.loads(output)
                    
                    for result in pylint_results:
                        severity_map = {
                            'error': Severity.HIGH,
                            'warning': Severity.MEDIUM,
                            'convention': Severity.LOW,
                            'refactor': Severity.MEDIUM
                        }
                        
                        issues.append(CodeIssue(
                            file_path=file_path,
                            line_start=result.get('line', 0),
                            line_end=result.get('line', 0),
                            issue_type=result.get('symbol', 'pylint-issue'),
                            severity=severity_map.get(result.get('type'), Severity.LOW),
                            description=result.get('message', ''),
                            suggestion="Review pylint suggestion"
                        ))
                except json.JSONDecodeError:
                    pass
                    
        except Exception as e:
            logger.warning(f"Pylint analysis failed for {file_path}: {e}")
            
        return issues
    
    def _analyze_structure(self, file_path: str, code: str) -> List[CodeIssue]:
        issues = []
        
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_lines = node.end_lineno - node.lineno + 1
                    if func_lines > self.max_method_lines:
                        issues.append(CodeIssue(
                            file_path=file_path,
                            line_start=node.lineno,
                            line_end=node.end_lineno,
                            issue_type="long_method",
                            severity=Severity.MEDIUM,
                            description=f"Function '{node.name}' is too long ({func_lines} lines)",
                            suggestion="Consider extracting sub-functions",
                            metric_value=func_lines
                        ))
                
                elif isinstance(node, ast.ClassDef):
                    class_lines = node.end_lineno - node.lineno + 1
                    if class_lines > self.max_class_lines:
                        issues.append(CodeIssue(
                            file_path=file_path,
                            line_start=node.lineno,
                            line_end=node.end_lineno,
                            issue_type="large_class",
                            severity=Severity.MEDIUM,
                            description=f"Class '{node.name}' is too large ({class_lines} lines)",
                            suggestion="Consider splitting into smaller classes",
                            metric_value=class_lines
                        ))
                        
        except Exception as e:
            logger.warning(f"AST analysis failed for {file_path}: {e}")
            
        return issues
    
    def _analyze_with_llm(self, file_path: str, code: str) -> List[CodeIssue]:
        issues = []
        
        try:
            if len(code) > 10000:
                logger.warning(f"Skipping LLM analysis for {file_path} (too large)")
                return issues
            
            response = self.llm_client.analyze_code(code, file_path)
            
            if response.success and response.content:
                try:
                    llm_issues = json.loads(response.content)
                    
                    for issue_data in llm_issues.get("issues", []):
                        severity_str = issue_data.get("severity", "MEDIUM")
                        severity = Severity[severity_str] if severity_str in Severity.__members__ else Severity.MEDIUM
                        
                        issues.append(CodeIssue(
                            file_path=file_path,
                            line_start=issue_data.get("line_start", 0),
                            line_end=issue_data.get("line_end", 0),
                            issue_type=issue_data.get("type", "llm-detected"),
                            severity=severity,
                            description=issue_data.get("description", ""),
                            suggestion=issue_data.get("suggestion")
                        ))
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse LLM response for {file_path}")
                    
        except Exception as e:
            logger.warning(f"LLM analysis failed for {file_path}: {e}")
            
        return issues
    
    def analyze_directory(self, directory: str) -> List[CodeIssue]:
        all_issues = []
        
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'venv', 'env', 'refactoring_reports']]
            
            for file in files:
                if file.endswith('.py') and not file.startswith('test_'):
                    file_path = os.path.join(root, file)
                    logger.info(f"Analyzing {file_path}")
                    issues = self.analyze_file(file_path)
                    all_issues.extend(issues)
                    logger.info(f"Found {len(issues)} issue(s) in {file_path}")
                    
        return sorted(all_issues, key=lambda x: (x.severity.value, x.file_path))