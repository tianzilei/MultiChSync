"""
Integration tests for CLI commands using CliRunner.

These tests use Click's CliRunner to test the CLI interface of multichsync.
Since the CLI uses argparse internally, we wrap it with a Click command.
"""

import sys
import pytest
from click import Command, Group
from click.testing import CliRunner


# Import the CLI main function
from multichsync.cli import main as cli_main


class ArgparseCliRunner(CliRunner):
    """
    A CliRunner that can invoke argparse-based CLI functions.

    This wraps an argparse main function to work with Click's CliRunner.
    """

    def __init__(self, cli_func, prog_name="multichsync"):
        super().__init__()
        self.cli_func = cli_func
        self.prog_name = prog_name

    def invoke(self, args=None, **kwargs):
        """Invoke the CLI with the given arguments."""
        if args is None:
            args = []
        if isinstance(args, str):
            args = args.split()

        # Save original argv
        original_argv = sys.argv

        exit_code = 0
        output = ""
        error_output = ""
        exception = None

        try:
            # Set up argv for the CLI
            sys.argv = [self.prog_name] + args

            # Capture stdout and stderr
            from io import StringIO

            old_stdout = sys.stdout
            old_stderr = sys.stderr
            stdout_capture = StringIO()
            stderr_capture = StringIO()

            try:
                sys.stdout = stdout_capture
                sys.stderr = stderr_capture

                # Call the CLI main function
                self.cli_func()

            except SystemExit as e:
                exit_code = e.code if e.code is not None else 0
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                output = stdout_capture.getvalue()
                error_output = stderr_capture.getvalue()

        except Exception as e:
            exception = e
            exit_code = 1
        finally:
            sys.argv = original_argv

        # Create a mock result object
        class Result:
            def __init__(self, exit_code, output, exception):
                self.exit_code = exit_code
                self.output = output + error_output
                self.exception = exception
                self.exception_info = None

        return Result(exit_code, output, exception)


# Create runner instances for each test
@pytest.fixture
def runner():
    """Create a CliRunner instance that works with argparse-based CLI."""
    return ArgparseCliRunner(cli_main)


class TestCliHelp:
    """Test CLI help commands."""

    def test_main_help(self, runner):
        """Test main help command shows multichsync."""
        result = runner.invoke(["--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "multichsync" in result.output.lower()
        assert "fnirs" in result.output.lower()
        assert "ecg" in result.output.lower()
        assert "eeg" in result.output.lower()
        assert "marker" in result.output.lower()
        assert "quality" in result.output.lower()

    def test_fnirs_help(self, runner):
        """Test fnirs subcommand help."""
        result = runner.invoke(["fnirs", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "fnirs" in result.output.lower()
        assert "convert" in result.output.lower()
        assert "batch" in result.output.lower()
        assert "patch" in result.output.lower()

    def test_marker_help(self, runner):
        """Test marker subcommand help."""
        result = runner.invoke(["marker", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "marker" in result.output.lower()
        assert "extract" in result.output.lower()
        assert "clean" in result.output.lower()
        assert "info" in result.output.lower()
        assert "match" in result.output.lower()

    def test_quality_help(self, runner):
        """Test quality subcommand help."""
        result = runner.invoke(["quality", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "quality" in result.output.lower()
        assert "assess" in result.output.lower()
        assert "batch" in result.output.lower()


class TestCliErrorHandling:
    """Test CLI error handling."""

    def test_missing_required_argument(self, runner):
        """Test error when required argument is missing."""
        # Test fnirs convert without required arguments
        result = runner.invoke(["fnirs", "convert"])

        # Should fail with error about missing required arguments
        assert result.exit_code != 0, (
            "Expected non-zero exit code for missing required arguments"
        )
        assert (
            "error" in result.output.lower()
            or "required" in result.output.lower()
            or "argument" in result.output.lower()
        )

    def test_invalid_subcommand(self, runner):
        """Test error for invalid subcommand."""
        # Test invalid fnirs subcommand
        result = runner.invoke(["fnirs", "invalid_command"])

        assert result.exit_code != 0, (
            "Expected non-zero exit code for invalid subcommand"
        )
        assert (
            "error" in result.output.lower()
            or "invalid" in result.output.lower()
            or "unknown" in result.output.lower()
        )

    def test_invalid_main_command(self, runner):
        """Test error for invalid main command."""
        result = runner.invoke(["invalid_command"])

        assert result.exit_code != 0, (
            "Expected non-zero exit code for invalid main command"
        )
        assert (
            "error" in result.output.lower()
            or "invalid" in result.output.lower()
            or "unknown" in result.output.lower()
        )


class TestCliMarkerCommands:
    """Test CLI marker subcommand help."""

    def test_marker_extract_help(self, runner):
        """Test marker extract help."""
        result = runner.invoke(["marker", "extract", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "extract" in result.output.lower()
        assert "--input" in result.output or "-i" in result.output

    def test_marker_clean_help(self, runner):
        """Test marker clean help."""
        result = runner.invoke(["marker", "clean", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "clean" in result.output.lower()
        assert "--input" in result.output or "-i" in result.output

    def test_marker_match_help(self, runner):
        """Test marker match help."""
        result = runner.invoke(["marker", "match", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "match" in result.output.lower()
        assert "--input-dir" in result.output or "--input-files" in result.output


class TestCliFnirsCommands:
    """Test CLI fnirs subcommand help."""

    def test_fnirs_convert_help(self, runner):
        """Test fnirs convert help."""
        result = runner.invoke(["fnirs", "convert", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "convert" in result.output.lower()
        assert "--txt-path" in result.output or "--txt" in result.output
        assert "--src-coords" in result.output
        assert "--det-coords" in result.output

    def test_fnirs_batch_help(self, runner):
        """Test fnirs batch help."""
        result = runner.invoke(["fnirs", "batch", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "batch" in result.output.lower()
        assert "--input-dir" in result.output or "-i" in result.output


class TestCliEcgCommands:
    """Test CLI ecg subcommand help."""

    def test_ecg_convert_help(self, runner):
        """Test ecg convert help."""
        result = runner.invoke(["ecg", "convert", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "convert" in result.output.lower()
        assert "--acq-path" in result.output or "--acq" in result.output

    def test_ecg_batch_help(self, runner):
        """Test ecg batch help."""
        result = runner.invoke(["ecg", "batch", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "batch" in result.output.lower()
        assert "--input-dir" in result.output or "-i" in result.output


class TestCliEegCommands:
    """Test CLI eeg subcommand help."""

    def test_eeg_convert_help(self, runner):
        """Test eeg convert help."""
        result = runner.invoke(["eeg", "convert", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "convert" in result.output.lower()
        assert "--file-path" in result.output or "--file" in result.output
        assert "--format" in result.output or "-f" in result.output

    def test_eeg_batch_help(self, runner):
        """Test eeg batch help."""
        result = runner.invoke(["eeg", "batch", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "batch" in result.output.lower()
        assert "--input-dir" in result.output or "-i" in result.output


class TestCliQualityCommands:
    """Test CLI quality subcommand help."""

    def test_quality_assess_help(self, runner):
        """Test quality assess help."""
        result = runner.invoke(["quality", "assess", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "assess" in result.output.lower()
        assert "--input" in result.output
        assert "--output-dir" in result.output

    def test_quality_batch_help(self, runner):
        """Test quality batch help."""
        result = runner.invoke(["quality", "batch", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "batch" in result.output.lower()
        assert "--input-dir" in result.output


class TestCliAdditionalCommands:
    """Test additional CLI commands help."""

    def test_marker_info_help(self, runner):
        """Test marker info help."""
        result = runner.invoke(["marker", "info", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "info" in result.output.lower()
        assert "--input-dir" in result.output

    def test_marker_batch_help(self, runner):
        """Test marker batch help."""
        result = runner.invoke(["marker", "batch", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "batch" in result.output.lower()
        assert "--types" in result.output or "-t" in result.output

    def test_quality_resting_metrics_help(self, runner):
        """Test quality resting-metrics help."""
        result = runner.invoke(["quality", "resting-metrics", "--help"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )
        assert "resting" in result.output.lower()
        assert "metrics" in result.output.lower()
        assert "--input-dir" in result.output
