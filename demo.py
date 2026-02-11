#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

def run_demo():
    print("=" * 60)
    print("Code Analysis & Refactoring Agent - Demo")
    print("=" * 60)
    
    venv_python = Path(__file__).parent / "venv" / "bin" / "python"
    main_script = Path(__file__).parent / "main.py"
    examples_dir = Path(__file__).parent / "examples"
    
    print("\n1. Running analysis on sample code...")
    print("-" * 60)
    
    result = subprocess.run(
        [str(venv_python), str(main_script), str(examples_dir), "--analysis-only"],
        capture_output=False,
        text=True
    )
    
    if result.returncode == 0:
        print("\n✓ Analysis completed successfully!")
    else:
        print("\n✗ Analysis failed!")
        return False
    
    print("\n2. Checking generated reports...")
    print("-" * 60)
    
    report_path = examples_dir / "refactoring_reports" / "analysis_report.json"
    if report_path.exists():
        print(f"✓ Analysis report found: {report_path}")
        
        import json
        with open(report_path) as f:
            report = json.load(f)
        
        print(f"\nReport Summary:")
        print(f"  Total Issues: {report.get('total_issues', 0)}")
        print(f"  Severity Breakdown: {report.get('severity_breakdown', {})}")
    else:
        print(f"✗ Report not found at {report_path}")
    
    print("\n3. Demo completed!")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    success = run_demo()
    sys.exit(0 if success else 1)