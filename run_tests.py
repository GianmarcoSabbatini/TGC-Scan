# TCG Scan - Test Runner Script
# Run this script to execute all tests

import subprocess
import sys

if __name__ == '__main__':
    # Run pytest with verbose output and coverage
    args = [
        sys.executable, '-m', 'pytest',
        'tests/',
        '-v',
        '--tb=short',
        '-x',  # Stop on first failure
    ]
    
    # Add coverage if available
    try:
        import pytest_cov
        args.extend(['--cov=.', '--cov-report=html', '--cov-report=term'])
    except ImportError:
        print("Note: Install pytest-cov for coverage reports")
    
    result = subprocess.run(args)
    sys.exit(result.returncode)
