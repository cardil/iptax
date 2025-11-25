#!/usr/bin/env python3
"""Fix trailing whitespace and ensure final newlines."""
import sys
from pathlib import Path

def fix_file(filepath: Path) -> bool:
    """Fix whitespace issues in a file. Returns True if modified."""
    try:
        content = filepath.read_text(encoding='utf-8')
        original = content

        # Fix trailing whitespace on each line
        lines = content.splitlines(keepends=True)
        fixed_lines = [
            line.rstrip() + ('\n' if line.endswith(('\n', '\r\n', '\r')) else '')
            for line in lines
        ]
        content = ''.join(fixed_lines)

        # Ensure final newline
        if content and not content.endswith('\n'):
            content += '\n'

        if content != original:
            filepath.write_text(content, encoding='utf-8')
            return True
        return False
    except (OSError, UnicodeError) as exc:
        print(f"Error processing {filepath}: {exc}", file=sys.stderr)
        return False

def main():
    """Fix whitespace in all relevant files."""
    patterns = ['*.md', '*.yml', '*.yaml', '*.toml', 'Makefile', '*.py']
    exclude_dirs = {
        '.venv', '.git', '__pycache__',
        '.pytest_cache', '.mypy_cache', '.ruff_cache'
    }

    root = Path('.')
    modified = []

    for pattern in patterns:
        for filepath in root.rglob(pattern):
            # Skip excluded directories
            if any(excluded in filepath.parts for excluded in exclude_dirs):
                continue

            if fix_file(filepath):
                modified.append(filepath)

    if modified:
        print(f"Fixed {len(modified)} files:")
        for f in sorted(modified):
            print(f"  {f}")
    else:
        print("No files needed fixing")

if __name__ == '__main__':
    main()
