#!/usr/bin/env python3
"""Code Quality Tests

This module enforces zero-tolerance policies for code quality issues:
- No linting errors (ruff)
- All issues must be fixed or explicitly marked with # noqa comments

ZERO TOLERANCE POLICY:
We maintain high code quality standards. Any linting error will fail the build.
If a linting error is a false positive, it must be explicitly suppressed with
a comment explaining why (e.g., # noqa: F401 - imported for re-export).
"""

import subprocess
from pathlib import Path

import pytest


class TestCodeQuality:
    """Test suite for enforcing code quality standards."""

    @pytest.fixture
    def project_root(self):
        """Get the project root directory."""
        # test/code_quality/test_code_quality.py -> test/code_quality -> test -> project_root
        return Path(__file__).parent.parent.parent

    @pytest.fixture
    def ruff_executable(self, project_root):
        """Get the path to the ruff executable."""
        venv_ruff = project_root / ".venv" / "bin" / "ruff"
        if venv_ruff.exists():
            return str(venv_ruff)

        # Try system ruff
        try:
            result = subprocess.run(["which", "ruff"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        pytest.skip("ruff not found - install with: pip install ruff")

    @pytest.fixture
    def pyright_executable(self, project_root):
        """Get the path to the pyright executable."""
        venv_pyright = project_root / ".venv" / "bin" / "pyright"
        if venv_pyright.exists():
            return str(venv_pyright)

        # Try system pyright
        try:
            result = subprocess.run(
                ["which", "pyright"], capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        # Try npx pyright
        try:
            result = subprocess.run(
                ["npx", "--version"], capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                return "npx pyright"
        except Exception:
            pass

        pytest.skip("pyright not found - install with: pip install pyright")

    def test_no_linting_errors(self, project_root, ruff_executable):
        """
        ZERO TOLERANCE: Enforce that there are no linting errors in the codebase.

        This test runs ruff on the entire codebase and fails if any linting
        issues are found. This enforces:

        - No unused imports
        - No undefined variables
        - Proper import ordering
        - No syntax errors
        - Consistent code style

        POLICY:
        - All linting errors MUST be fixed
        - False positives MUST be suppressed with # noqa comments
        - Each suppression MUST include an explanation

        Examples of acceptable suppressions:
            from module import foo  # noqa: F401 - imported for re-export
            x = calculate()  # noqa: F841 - used in debugging
        """
        # Directories to check
        check_dirs = ["app", "test", "scripts"]

        # Run ruff check
        result = subprocess.run(
            [ruff_executable, "check"] + check_dirs + ["--output-format=concise", "--no-fix"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            error_message = [
                "",
                "=" * 80,
                "ZERO TOLERANCE POLICY VIOLATION: LINTING ERRORS DETECTED",
                "=" * 80,
                "",
                "We maintain a zero-tolerance policy for linting errors.",
                "All code must pass linting checks before being committed.",
                "",
                "LINTING ERRORS FOUND:",
                "",
                result.stdout,
                "",
                "HOW TO FIX:",
                "",
                "1. Run automatic fixes:",
                f"   {ruff_executable} check {' '.join(check_dirs)} --fix",
                "",
                "2. For false positives, add # noqa comment with explanation:",
                "   from module import foo  # noqa: F401 - imported for re-export",
                "",
                "3. Review and commit the changes",
                "",
                "COMMON ISSUES:",
                "",
                "- F401: Unused import - remove or add # noqa with reason",
                "- F841: Unused variable - remove or add # noqa with reason",
                "- E402: Module level import not at top - move import or add # noqa",
                "",
                "For more information: https://docs.astral.sh/ruff/rules/",
                "",
                "=" * 80,
            ]

            pytest.fail("\n".join(error_message))

    def test_no_type_errors(self, project_root, pyright_executable):
        """
        ZERO TOLERANCE: Enforce that there are no type errors in the codebase.

        This test runs pyright (the type checker that powers Pylance) on the
        entire codebase and fails if any type errors are found. This catches:

        - Type mismatches in function arguments
        - Invalid attribute access
        - Incorrect return types
        - Type annotation errors

        POLICY:
        - All type errors MUST be fixed
        - Use proper type annotations
        - For legitimate dynamic typing, use proper type hints (Any, cast, etc.)

        Examples of fixes:
            # Fix type mismatch:
            def foo(x: int) -> str:  # Declare proper types
                return str(x)

            # For dynamic types:
            from typing import Any
            def bar(x: Any) -> Any:  # Use Any when needed
                return x
        """
        # Directories to check
        check_dirs = ["app", "test", "scripts"]

        # Run pyright check
        cmd = pyright_executable.split() + check_dirs
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
        )

        # Pyright returns 0 for success, 1 for errors
        if result.returncode != 0:
            error_message = [
                "",
                "=" * 80,
                "ZERO TOLERANCE POLICY VIOLATION: TYPE ERRORS DETECTED",
                "=" * 80,
                "",
                "We maintain a zero-tolerance policy for type errors.",
                "All code must pass type checking before being committed.",
                "These are the same errors that Pylance shows in VS Code.",
                "",
                "TYPE ERRORS FOUND:",
                "",
                result.stdout,
                "",
                result.stderr if result.stderr else "",
                "",
                "HOW TO FIX:",
                "",
                "1. Add or correct type annotations:",
                "   def my_func(x: int, y: str) -> bool:",
                "",
                "2. Use proper type hints for complex types:",
                "   from typing import Dict, List, Optional, Union",
                "   def process(data: Dict[str, List[int]]) -> Optional[str]:",
                "",
                "3. For dynamic types, use Any:",
                "   from typing import Any",
                "   def dynamic_func(x: Any) -> Any:",
                "",
                "4. Use type: ignore for unavoidable issues:",
                "   result = some_untyped_lib()  # type: ignore[attr-defined]",
                "",
                "For more information:",
                "https://microsoft.github.io/pyright/",
                "",
                "=" * 80,
            ]

            pytest.fail("\n".join(error_message))

    def test_ruff_configuration_exists(self, project_root):
        """Verify that ruff configuration exists in pyproject.toml."""
        pyproject = project_root / "pyproject.toml"
        assert pyproject.exists(), "pyproject.toml not found"

        content = pyproject.read_text()
        assert "[tool.ruff]" in content, "ruff configuration not found in pyproject.toml"

    def test_no_syntax_errors(self, project_root):
        """
        Verify that all Python files have valid syntax.

        This is a basic check that complements ruff linting.
        """
        python_files = []
        for directory in ["app", "test", "scripts"]:
            dir_path = project_root / directory
            if dir_path.exists():
                python_files.extend(dir_path.rglob("*.py"))

        syntax_errors = []
        for py_file in python_files:
            try:
                compile(py_file.read_text(), str(py_file), "exec")
            except SyntaxError as e:
                syntax_errors.append(f"{py_file}: {e}")

        if syntax_errors:
            error_message = (
                [
                    "",
                    "=" * 80,
                    "SYNTAX ERRORS DETECTED",
                    "=" * 80,
                    "",
                    "The following files have syntax errors:",
                    "",
                ]
                + syntax_errors
                + [
                    "",
                    "=" * 80,
                ]
            )
            pytest.fail("\n".join(error_message))


class TestCodeQualityMetrics:
    """Optional metrics tests that provide insights but don't fail the build."""

    @pytest.fixture
    def project_root(self):
        """Get the project root directory."""
        return Path(__file__).parent.parent

    @pytest.fixture
    def ruff_executable(self, project_root):
        """Get the path to the ruff executable."""
        venv_ruff = project_root / ".venv" / "bin" / "ruff"
        if venv_ruff.exists():
            return str(venv_ruff)

        try:
            result = subprocess.run(["which", "ruff"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        pytest.skip("ruff not found")

    def test_code_statistics(self, project_root, ruff_executable):
        """
        Generate code quality statistics (informational only).

        This test always passes but prints useful statistics.
        """
        # Count Python files
        python_files = []
        for directory in ["app", "test", "scripts"]:
            dir_path = project_root / directory
            if dir_path.exists():
                python_files.extend(dir_path.rglob("*.py"))

        # Count lines of code
        total_lines = 0
        for py_file in python_files:
            try:
                total_lines += len(py_file.read_text().splitlines())
            except Exception:
                pass

        print("\n\nCode Quality Statistics:")
        print(f"  Python files: {len(python_files)}")
        print(f"  Total lines: {total_lines:,}")
        print(
            f"  Average lines per file: {total_lines // len(python_files) if python_files else 0}"
        )

        # This test always passes - it's just informational
        assert True
