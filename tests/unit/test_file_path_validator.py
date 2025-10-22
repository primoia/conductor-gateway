"""
Unit tests for file path validation utilities.
"""

import pytest
from src.utils.file_path_validator import (
    validate_file_path,
    sanitize_file_path,
    get_safe_filename,
    is_relative_path,
)


@pytest.mark.unit
class TestValidateFilePath:
    """Test validate_file_path function."""

    def test_validate_file_path_none(self):
        """Test validation with None (should be valid)."""
        assert validate_file_path(None) is True

    def test_validate_file_path_empty_string(self):
        """Test validation with empty string (should be invalid)."""
        assert validate_file_path("") is False
        assert validate_file_path("   ") is False

    def test_validate_file_path_not_string(self):
        """Test validation with non-string input (should be invalid)."""
        assert validate_file_path(123) is False
        assert validate_file_path([]) is False
        assert validate_file_path({}) is False

    def test_validate_file_path_path_traversal(self):
        """Test validation with path traversal attempts (should be invalid)."""
        assert validate_file_path("../file.md") is False
        assert validate_file_path("../../file.md") is False
        assert validate_file_path("folder/../file.md") is False
        assert validate_file_path("/absolute/path/file.md") is False

    def test_validate_file_path_dangerous_chars(self):
        """Test validation with dangerous characters (should be invalid)."""
        dangerous_paths = [
            "file<.md",
            "file>.md",
            "file:.md",
            'file".md',
            "file|.md",
            "file?.md",
            "file*.md",
            "file\x00.md",
        ]
        for path in dangerous_paths:
            assert validate_file_path(path) is False, f"Path {path} should be invalid"

    def test_validate_file_path_invalid_extensions(self):
        """Test validation with invalid file extensions (should be invalid)."""
        invalid_extensions = [
            "file.exe",
            "file.py",
            "file.js",
            "file.html",
            "file",
            "file.",
        ]
        for path in invalid_extensions:
            assert validate_file_path(path) is False, f"Path {path} should be invalid"

    def test_validate_file_path_valid_extensions(self):
        """Test validation with valid file extensions (should be valid)."""
        valid_extensions = [
            "file.md",
            "file.txt",
            "file.markdown",
            "FILE.MD",  # Case insensitive
            "FILE.TXT",
            "FILE.MARKDOWN",
        ]
        for path in valid_extensions:
            assert validate_file_path(path) is True, f"Path {path} should be valid"

    def test_validate_file_path_too_long(self):
        """Test validation with path too long (should be invalid)."""
        long_path = "a" * 501 + ".md"
        assert validate_file_path(long_path) is False

    def test_validate_file_path_double_slashes(self):
        """Test validation with double slashes (should be invalid)."""
        assert validate_file_path("folder//file.md") is False
        assert validate_file_path("//file.md") is False

    def test_validate_file_path_backslash_start(self):
        """Test validation with backslash start (should be invalid)."""
        assert validate_file_path("\\file.md") is False

    def test_validate_file_path_valid_paths(self):
        """Test validation with valid paths (should be valid)."""
        valid_paths = [
            "file.md",
            "folder/file.md",
            "folder/subfolder/file.md",
            "file.txt",
            "file.markdown",
            "folder/file.txt",
            "folder/subfolder/file.markdown",
        ]
        for path in valid_paths:
            assert validate_file_path(path) is True, f"Path {path} should be valid"


@pytest.mark.unit
class TestSanitizeFilePath:
    """Test sanitize_file_path function."""

    def test_sanitize_file_path_none(self):
        """Test sanitization with None (should return None)."""
        assert sanitize_file_path(None) is None

    def test_sanitize_file_path_not_string(self):
        """Test sanitization with non-string input (should return None)."""
        assert sanitize_file_path(123) is None
        assert sanitize_file_path([]) is None

    def test_sanitize_file_path_empty_string(self):
        """Test sanitization with empty string (should return None)."""
        assert sanitize_file_path("") is None
        assert sanitize_file_path("   ") is None

    def test_sanitize_file_path_whitespace(self):
        """Test sanitization with leading/trailing whitespace."""
        assert sanitize_file_path("  file.md  ") == "file.md"

    def test_sanitize_file_path_backslashes(self):
        """Test sanitization with backslashes."""
        assert sanitize_file_path("folder\\file.md") == "folder/file.md"

    def test_sanitize_file_path_double_slashes(self):
        """Test sanitization with double slashes."""
        assert sanitize_file_path("folder//file.md") == "folder/file.md"
        assert sanitize_file_path("folder///file.md") == "folder/file.md"

    def test_sanitize_file_path_leading_slash(self):
        """Test sanitization with leading slash."""
        assert sanitize_file_path("/file.md") == "file.md"
        assert sanitize_file_path("//file.md") == "file.md"

    def test_sanitize_file_path_invalid_after_sanitization(self):
        """Test sanitization with path that becomes invalid."""
        # Path with dangerous characters that can't be sanitized
        assert sanitize_file_path("file<.md") is None
        assert sanitize_file_path("../file.md") is None

    def test_sanitize_file_path_valid_after_sanitization(self):
        """Test sanitization with path that becomes valid."""
        assert sanitize_file_path("  folder/file.md  ") == "folder/file.md"
        assert sanitize_file_path("folder\\file.md") == "folder/file.md"


@pytest.mark.unit
class TestGetSafeFilename:
    """Test get_safe_filename function."""

    def test_get_safe_filename_valid_path(self):
        """Test getting filename from valid path."""
        assert get_safe_filename("folder/file.md") == "file.md"
        assert get_safe_filename("file.md") == "file.md"
        assert get_safe_filename("folder/subfolder/file.txt") == "file.txt"

    def test_get_safe_filename_invalid_path(self):
        """Test getting filename from invalid path."""
        assert get_safe_filename("../file.md") == ""
        assert get_safe_filename("file<.md") == ""
        assert get_safe_filename("") == ""

    def test_get_safe_filename_none(self):
        """Test getting filename from None."""
        assert get_safe_filename(None) == ""


@pytest.mark.unit
class TestIsRelativePath:
    """Test is_relative_path function."""

    def test_is_relative_path_relative(self):
        """Test with relative paths (should return True)."""
        relative_paths = [
            "file.md",
            "folder/file.md",
            "folder/subfolder/file.md",
        ]
        for path in relative_paths:
            assert is_relative_path(path) is True, f"Path {path} should be relative"

    def test_is_relative_path_absolute_unix(self):
        """Test with absolute Unix paths (should return False)."""
        assert is_relative_path("/file.md") is False
        assert is_relative_path("/folder/file.md") is False

    def test_is_relative_path_absolute_windows(self):
        """Test with absolute Windows paths (should return False)."""
        assert is_relative_path("C:file.md") is False
        assert is_relative_path("C:\\file.md") is False
        assert is_relative_path("D:\\folder\\file.md") is False

    def test_is_relative_path_empty(self):
        """Test with empty path (should return False)."""
        assert is_relative_path("") is False
        assert is_relative_path(None) is False