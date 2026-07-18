"""输出文件路径构建器。"""

from __future__ import annotations

import re
from pathlib import Path

from douyin_dl.models import VideoMeta


# Characters that are illegal in filenames on Windows AND/OR Linux/macOS.
ILLEGAL_CHARS_RE = re.compile(r'[\/\\\:\*\?\"\<\>\|\x00-\x1f]')

# Max filename length (excluding extension and directory path). Most filesystems allow 255
# bytes, but we keep it conservative at 100 chars to leave room for suffixes.
MAX_FILENAME_LENGTH = 100

# Leading/trailing characters to remove: whitespace, dots, underscores.
# Underscores are included so that components consisting solely of illegal chars
# (which get replaced with underscores) collapse to empty and fall back.
_STRIP_CHARS = " \t\n\r\v\f._"


class FileNamer:
    """Build output file paths for downloaded videos."""

    @staticmethod
    def sanitize_component(text: str, fallback: str) -> str:
        """Sanitize a single component (author or title).
        - Replace illegal chars (and control chars) with '_'.
        - Strip leading/trailing whitespace and dots.
        - If empty after sanitizing, return fallback.
        """
        if text is None:
            text = ""
        # Replace illegal chars (and control chars) with '_'.
        text = ILLEGAL_CHARS_RE.sub("_", text)
        # Strip leading/trailing whitespace, dots, and underscores.
        text = text.strip(_STRIP_CHARS)
        # Collapse multiple consecutive underscores into one.
        text = re.sub(r"_{2,}", "_", text)
        # Strip again after collapse.
        text = text.strip(_STRIP_CHARS)
        # If empty after sanitizing, return fallback.
        if not text:
            return fallback
        return text

    @staticmethod
    def build(meta: VideoMeta, output_dir: Path) -> Path:
        """Build the full output path: output_dir / {author}_{title}_{aweme_id}.mp4
        - author: sanitize, fallback "unknown"
        - title: sanitize, fallback "untitled"
        - aweme_id: taken as-is (always digits, safe)
        - Truncate the entire filename (excluding .mp4 extension) to MAX_FILENAME_LENGTH chars.
        - Returns Path object; does NOT create the directory.
        """
        author = FileNamer.sanitize_component(meta.author, "unknown")
        title = FileNamer.sanitize_component(meta.title, "untitled")
        # aweme_id is assumed to be digits, but sanitize just in case.
        aweme_id = ILLEGAL_CHARS_RE.sub("_", meta.aweme_id)

        # Keep aweme_id intact at the end (unique identifier), truncate the middle.
        aweme_suffix = f"_{aweme_id}"
        available = MAX_FILENAME_LENGTH - len(aweme_suffix)
        if available < 0:
            available = 0
        prefix = f"{author}_{title}"[:available]
        base_name = prefix + aweme_suffix

        filename = f"{base_name}.mp4"
        return Path(output_dir) / filename
