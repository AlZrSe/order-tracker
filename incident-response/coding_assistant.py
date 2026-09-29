#!/usr/bin/env python3
"""
Simple coding assistant for incident response testing.
This simulates an AI coding assistant that analyzes incidents and provides recommendations.
"""

import sys
import json
import os
from pathlib import Path

def analyze_incident(prompt: str) -> str:
    """Analyze the incident and provide recommendations."""
    
    analysis = """# Incident Analysis Report

## Root Cause Analysis
Based on the incident data, this appears to be a test alert with no actual incident to fix.

## Immediate Mitigation Steps
1. Verify this is a test alert (confirmed: ResponderTest)
2. No action required for production systems

## Long-term Fix Recommendations
1. Configure proper alerting rules for production
2. Set up notification channels (Slack, PagerDuty, etc.)
3. Define runbooks for common incident types

## Code Changes Needed
None required for this test alert.
"""
    return analysis

def main():
    # Read prompt from stdin or file
    prompt = sys.stdin.read()
    
    # Also check for prompt file argument
    prompt_file = None
    for arg in sys.argv[1:]:
        if arg.endswith('.txt') and os.path.exists(arg):
            prompt_file = arg
            break
    
    if prompt_file:
        with open(prompt_file, 'r') as f:
            prompt = f.read()
    
    # Analyze
    analysis = analyze_incident(prompt)
    
    # Output analysis
    print(analysis)
    
    # Write to ANALYSIS.md if in a working directory
    cwd = os.getcwd()
    analysis_file = Path(cwd) / "ANALYSIS.md"
    try:
        analysis_file.write_text(analysis)
    except Exception:
        pass
    
    return 0

if __name__ == "__main__":
    sys.exit(main())