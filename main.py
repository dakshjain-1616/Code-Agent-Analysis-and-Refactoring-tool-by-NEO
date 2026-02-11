#!/usr/bin/env python3
import os
import sys
import logging
import yaml
import json
from pathlib import Path
from typing import Dict, List
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress
import pandas as pd

from src.llm import LLMClient
from src.analysis import CodeAnalyzer, CodeIssue
from src.git_ops import GitManager
from src.runner import TestRunner
from src.refactor import RefactoringAgent, RefactoringResult

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('refactoring_agent.log')
    ]
)
logger = logging.getLogger(__name__)
console = Console()


def load_config(config_path: str) -> Dict:
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


def generate_analysis_report(issues: List[CodeIssue], output_path: str):
    console.print("\n[bold cyan]Code Analysis Report[/bold cyan]")
    
    if not issues:
        console.print("[green]No issues found! Code looks good.[/green]")
        return
    
    table = Table(title="Identified Code Smells")
    table.add_column("File", style="cyan")
    table.add_column("Line", style="magenta")
    table.add_column("Type", style="yellow")
    table.add_column("Severity", style="red")
    table.add_column("Description", style="white")
    
    for issue in issues[:20]:
        severity_color = {
            "CRITICAL": "[red]",
            "HIGH": "[orange1]",
            "MEDIUM": "[yellow]",
            "LOW": "[green]"
        }.get(issue.severity.value, "")
        
        table.add_row(
            str(Path(issue.file_path).name),
            str(issue.line_start),
            issue.issue_type,
            f"{severity_color}{issue.severity.value}[/]",
            issue.description[:60] + "..." if len(issue.description) > 60 else issue.description
        )
    
    console.print(table)
    
    severity_counts = {}
    for issue in issues:
        severity_counts[issue.severity.value] = severity_counts.get(issue.severity.value, 0) + 1
    
    console.print("\n[bold]Summary by Severity:[/bold]")
    for severity, count in severity_counts.items():
        console.print(f"  {severity}: {count}")
    
    try:
        report_data = {
            "total_issues": len(issues),
            "severity_breakdown": severity_counts,
            "issues": [issue.to_dict() for issue in issues]
        }
        
        with open(output_path, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        console.print(f"\n[green]Analysis report saved to: {output_path}[/green]")
    except Exception as e:
        logger.error(f"Failed to save report: {e}")


def generate_refactoring_report(results: List[RefactoringResult], 
                                issues_before: List[CodeIssue],
                                issues_after: List[CodeIssue],
                                output_path: str):
    console.print("\n[bold cyan]Refactoring Results Report[/bold cyan]")
    
    table = Table(title="Applied Refactorings")
    table.add_column("File", style="cyan")
    table.add_column("Issue Type", style="yellow")
    table.add_column("Status", style="green")
    table.add_column("Tests", style="magenta")
    table.add_column("Commit", style="blue")
    
    for result in results:
        status = "✓ Applied" if result.applied else "✗ Failed"
        status_color = "green" if result.applied else "red"
        
        tests = "✓ Passed" if result.test_passed else "✗ Failed"
        tests_color = "green" if result.test_passed else "red"
        
        table.add_row(
            str(Path(result.issue.file_path).name),
            result.issue.issue_type,
            f"[{status_color}]{status}[/]",
            f"[{tests_color}]{tests}[/]",
            result.commit_hash or "N/A"
        )
    
    console.print(table)
    
    successful = sum(1 for r in results if r.success)
    console.print(f"\n[bold]Refactoring Summary:[/bold]")
    console.print(f"  Total attempts: {len(results)}")
    console.print(f"  Successful: {successful}")
    console.print(f"  Failed: {len(results) - successful}")
    
    console.print(f"\n[bold]Code Quality Metrics:[/bold]")
    console.print(f"  Issues before: {len(issues_before)}")
    console.print(f"  Issues after: {len(issues_after)}")
    console.print(f"  Improvement: {len(issues_before) - len(issues_after)} issues resolved")
    
    try:
        report_data = {
            "refactoring_summary": {
                "total_attempts": len(results),
                "successful": successful,
                "failed": len(results) - successful
            },
            "metrics": {
                "issues_before": len(issues_before),
                "issues_after": len(issues_after),
                "issues_resolved": len(issues_before) - len(issues_after)
            },
            "results": [
                {
                    "file": result.issue.file_path,
                    "issue_type": result.issue.issue_type,
                    "success": result.success,
                    "test_passed": result.test_passed,
                    "commit_hash": result.commit_hash,
                    "error": result.error
                }
                for result in results
            ]
        }
        
        with open(output_path, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        console.print(f"\n[green]Refactoring report saved to: {output_path}[/green]")
    except Exception as e:
        logger.error(f"Failed to save refactoring report: {e}")


@click.command()
@click.argument('target_directory', type=click.Path(exists=True))
@click.option('--config', '-c', default='config.yaml', help='Path to configuration file')
@click.option('--model', '-m', help='Override LLM model from config')
@click.option('--auto-apply', is_flag=True, help='Automatically apply refactorings')
@click.option('--max-issues', default=10, help='Maximum issues to refactor')
@click.option('--analysis-only', is_flag=True, help='Run analysis without refactoring')
def main(target_directory, config, model, auto_apply, max_issues, analysis_only):
    console.print(Panel.fit(
        "[bold cyan]Code Analysis & Refactoring Agent[/bold cyan]\n"
        "Autonomous code improvement powered by LLM",
        border_style="cyan"
    ))
    
    target_dir = Path(target_directory).resolve()
    console.print(f"\n[yellow]Target Directory:[/yellow] {target_dir}")
    
    config_path = Path(config)
    if not config_path.exists():
        config_path = Path(__file__).parent / "config.yaml"
    
    cfg = load_config(str(config_path))
    
    if model:
        cfg.setdefault('llm', {})['model'] = model
    
    if auto_apply:
        cfg.setdefault('refactoring', {})['auto_apply'] = True
    
    console.print(f"[yellow]Configuration:[/yellow] {config_path}")
    console.print(f"[yellow]LLM Model:[/yellow] {cfg.get('llm', {}).get('model', 'N/A')}")
    
    with Progress() as progress:
        task = progress.add_task("[cyan]Initializing components...", total=4)
        
        try:
            llm_client = LLMClient(cfg)
            progress.update(task, advance=1)
            
            analyzer = CodeAnalyzer(cfg, llm_client)
            progress.update(task, advance=1)
            
            git_manager = GitManager(str(target_dir), cfg)
            progress.update(task, advance=1)
            
            test_runner = TestRunner(cfg)
            progress.update(task, advance=1)
            
        except Exception as e:
            console.print(f"[red]Initialization failed: {e}[/red]")
            logger.error(f"Initialization error: {e}", exc_info=True)
            sys.exit(1)
    
    console.print("\n[bold green]✓ Components initialized[/bold green]")
    
    console.print("\n[cyan]Running code analysis...[/cyan]")
    issues = analyzer.analyze_directory(str(target_dir))
    
    output_dir = target_dir / "refactoring_reports"
    output_dir.mkdir(exist_ok=True)
    
    analysis_report_path = output_dir / "analysis_report.json"
    generate_analysis_report(issues, str(analysis_report_path))
    
    if analysis_only:
        console.print("\n[yellow]Analysis complete. Skipping refactoring (--analysis-only flag set)[/yellow]")
        return
    
    if not issues:
        console.print("\n[green]No issues found. Nothing to refactor![/green]")
        return
    
    console.print(f"\n[cyan]Starting refactoring process (max {max_issues} issues)...[/cyan]")
    
    refactoring_agent = RefactoringAgent(cfg, llm_client, git_manager, test_runner)
    results = refactoring_agent.run_refactoring_loop(issues, str(target_dir), max_issues)
    
    console.print("\n[cyan]Running post-refactoring analysis...[/cyan]")
    issues_after = analyzer.analyze_directory(str(target_dir))
    
    refactoring_report_path = output_dir / "refactoring_report.json"
    generate_refactoring_report(results, issues, issues_after, str(refactoring_report_path))
    
    console.print("\n[bold green]✓ Refactoring process complete![/bold green]")
    console.print(f"\n[cyan]Reports saved in: {output_dir}[/cyan]")


if __name__ == "__main__":
    main()