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

import json
import subprocess
from pathlib import Path
from typing import TypedDict

import pytest

from app.logger import session_logger as logger


class _RadonOffender(TypedDict):
    file: str
    function: str
    line: int
    cc: int
    grade: str


class TestCodeQuality:
    """Test suite for enforcing code quality standards."""

    _MAX_SOURCE_LINES = 1000
    _LARGE_FILE_ALLOWLIST = {
        Path("app/mcp_server/mcp_server.py"),
    }

    _RADON_MAX_OFFENDERS = 10
    _RADON_ALLOWLIST: set[tuple[str, str]] = {
        ("app/mcp_server/mcp_server.py", "_handle_get_content"),
        ("app/processing/news_parser.py", "_story_from_block"),
    }

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

    @pytest.fixture
    def radon_executable(self, project_root):
        """Get the path to the radon executable."""
        venv_radon = project_root / ".venv" / "bin" / "radon"
        if venv_radon.exists():
            return str(venv_radon)

        try:
            result = subprocess.run(["which", "radon"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        pytest.skip("radon not found - install with: uv add --group dev radon")

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
        check_dirs = ["app", "test", "scripts", "simulator"]

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
        check_dirs = ["app", "test", "scripts", "simulator"]

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

    def test_no_very_large_source_files(self, project_root):
        """Pragmatic gate: fail if app/ contains very large Python source files.

        This is complementary to Ruff/Pyright/Radon:
        - It does not measure complexity; it measures reviewability/maintainability risk.
        - Scope is intentionally limited to runtime code (app/).
        """

        app_dir = project_root / "app"
        if not app_dir.exists():
            pytest.skip("app/ directory not found")

        offenders: list[tuple[Path, int]] = []
        for py_file in sorted(app_dir.rglob("*.py")):
            if py_file.name == "__init__.py":
                continue

            rel_path = py_file.relative_to(project_root)
            if rel_path in self._LARGE_FILE_ALLOWLIST:
                logger.warning(
                    "code_quality.large_file_allowlisted",
                    event="code_quality.large_file_allowlisted",
                    path=str(rel_path),
                    recovery="Refactor/split the module and remove it from the allowlist",
                )
                continue

            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                pytest.fail(f"Failed to read {py_file}: {type(exc).__name__}: {exc}")

            line_count = len(content.splitlines())
            if line_count > self._MAX_SOURCE_LINES:
                offenders.append((py_file, line_count))

        if offenders:
            lines = [
                "",
                "=" * 80,
                "CODE QUALITY VIOLATION: LARGE_SOURCE_FILE",
                "=" * 80,
                "",
                f"Policy: app/ Python files (excluding __init__.py) must be <= {self._MAX_SOURCE_LINES} lines.",
                "",
                "Offenders:",
            ]

            for path, count in offenders:
                rel = path.relative_to(project_root)
                lines.append(f"- {rel} (lines={count}, limit={self._MAX_SOURCE_LINES})")

            lines += [
                "",
                "How to remediate (pick the smallest change that improves structure):",
                "- Split the module into smaller modules (e.g., move helpers into a sibling file).",
                "- Extract helper functions/classes to reduce file length and isolate responsibilities.",
                "- Separate IO/networking from parsing/processing logic.",
                "",
                "=" * 80,
            ]

            pytest.fail("\n".join(lines))

    def test_no_excessive_cyclomatic_complexity(self, project_root, radon_executable):
        """Pragmatic gate: fail on clearly excessive cyclomatic complexity in app/.

        Implementation notes:
        - Uses radon JSON output and emits a deterministic summary (LLM-friendly).
        - Fails only for high grades:
          - E/F anywhere in app/
          - D anywhere in app/
        """

        app_dir = project_root / "app"
        if not app_dir.exists():
            pytest.skip("app/ directory not found")

        result = subprocess.run(
            [radon_executable, "cc", "-j", "app"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            pytest.fail(
                "\n".join(
                    [
                        "",
                        "=" * 80,
                        "CODE QUALITY VIOLATION: RADON_EXECUTION_FAILED",
                        "=" * 80,
                        "",
                        "Cause: radon returned a non-zero exit code.",
                        "",
                        "Stdout:",
                        result.stdout,
                        "",
                        "Stderr:",
                        result.stderr,
                        "",
                        "Recovery: ensure radon is installed (uv add --group dev radon) and rerun.",
                        "",
                        "=" * 80,
                    ]
                )
            )

        try:
            payload = json.loads(result.stdout or "{}")
        except Exception as exc:
            pytest.fail(f"Failed to parse radon JSON output: {type(exc).__name__}: {exc}")

        offenders: list[_RadonOffender] = []
        allowlisted_hits: list[_RadonOffender] = []

        if not isinstance(payload, dict):
            pytest.fail("Radon JSON output has unexpected top-level type")

        for raw_file_path, blocks in payload.items():
            if not isinstance(raw_file_path, str):
                continue

            file_path = Path(raw_file_path)
            if file_path.is_absolute():
                try:
                    file_path = file_path.relative_to(project_root)
                except Exception:
                    continue

            # Normalize to repo-relative POSIX path.
            file_rel = file_path.as_posix()

            if not file_rel.startswith("app/"):
                continue
            if file_path.name == "__init__.py":
                continue

            if not isinstance(blocks, list):
                continue

            for block in blocks:
                if not isinstance(block, dict):
                    continue

                name = block.get("name")
                lineno = block.get("lineno")
                complexity = block.get("complexity")
                rank = block.get("rank")

                if not isinstance(name, str):
                    continue
                if not isinstance(lineno, int):
                    lineno = 0
                if not isinstance(complexity, int):
                    continue

                grade = str(rank) if isinstance(rank, str) else _cc_grade(complexity)
                grade = grade.upper()

                # Pragmatic thresholds for initial rollout (app/ only).
                if grade not in {"D", "E", "F"}:
                    continue

                key = (file_rel, name)
                entry: _RadonOffender = {
                    "file": file_rel,
                    "function": name,
                    "line": lineno,
                    "cc": complexity,
                    "grade": grade,
                }

                if key in self._RADON_ALLOWLIST:
                    allowlisted_hits.append(entry)
                else:
                    offenders.append(entry)

        # Warn on allowlisted complexity hotspots so they stay visible.
        for entry in allowlisted_hits:
            logger.warning(
                "code_quality.complexity_allowlisted",
                event="code_quality.complexity_allowlisted",
                path=entry["file"],
                function=entry["function"],
                grade=entry["grade"],
                cc=entry["cc"],
                recovery="Refactor/split the function and remove it from the Radon allowlist",
            )

        if not offenders:
            return

        offenders.sort(
            key=lambda e: (_grade_severity(e["grade"]), e["cc"]),
            reverse=True,
        )

        top = offenders[: self._RADON_MAX_OFFENDERS]
        lines: list[str] = [
            "",
            "=" * 80,
            "CODE QUALITY VIOLATION: COMPLEXITY_VIOLATION",
            "=" * 80,
            "",
            "Policy: app/ functions must not exceed cyclomatic complexity grade D/E/F thresholds.",
            "",
        ]

        for entry in top:
            file_path = entry["file"]
            function = entry["function"]
            line = entry["line"]
            cc = entry["cc"]
            grade = entry["grade"]

            lines += [
                "COMPLEXITY_VIOLATION",
                f"file: {file_path}",
                f"function: {function}",
                f"line: {line}",
                f"cc: {cc}",
                f"grade: {grade}",
                "why: cyclomatic complexity exceeds allowed threshold",
                "action: split into helper functions; reduce nesting via early returns; separate IO from parsing",
                "",
            ]

        lines += [
            "To remediate: open the file/function above and refactor to reduce branching; keep behavior identical; add/adjust tests.",
            "",
            "=" * 80,
        ]

        pytest.fail("\n".join(lines))


def _cc_grade(complexity: int) -> str:
    if complexity <= 5:
        return "A"
    if complexity <= 10:
        return "B"
    if complexity <= 20:
        return "C"
    if complexity <= 30:
        return "D"
    if complexity <= 40:
        return "E"
    return "F"


def _grade_severity(grade: str) -> int:
    # Higher is more severe.
    order = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}
    return order.get(grade.upper(), 0)


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
