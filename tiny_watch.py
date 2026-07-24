"""
tiny-watch — Zero-dependency file watcher with debounce, coalescing, and glob filtering.
MIT License. https://github.com/hussain-alsaibai/tiny-watch
"""
from __future__ import annotations
import os
import sys
import time
import stat
import hashlib
import threading
import asyncio
import fnmatch
from typing import Iterator, Optional, Callable
from dataclasses import dataclass
from pathlib import Path

__version__ = "1.0.0"
__all__ = ["watch", "ignore", "AsyncWatcher", "FileEvent"]


# ── Event types ───────────────────────────────────────────────────────────────

@dataclass
class FileEvent:
    """Represents a file system event."""
    type: str          # "created", "modified", "deleted", "renamed"
    path: str          # Full path to the file
    src_path: Optional[str] = None  # Original path (for renames)
    dst_path: Optional[str] = None  # New path (for renames)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


# ── Glob utilities ────────────────────────────────────────────────────────────

def _match_any(path: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    name = os.path.basename(path)
    full = path
    for p in patterns:
        if fnmatch.fnmatch(name, p) or fnmatch.fnmatch(full, p):
            return True
    return False


def _match_ignore(path: str, patterns: list[str]) -> bool:
    if not patterns:
        return False
    name = os.path.basename(path)
    full = path
    for p in patterns:
        if fnmatch.fnmatch(name, p) or fnmatch.fnmatch(full, p):
            return True
    return False


# ── Native watcher (best available) ─────────────────────────────────────────

def _native_walk(
    path: str,
    recursive: bool,
    patterns: list[str],
    ignore_patterns: list[str],
    last_mtimes: dict[str, float],
) -> Iterator[FileEvent]:
    """Walk a directory tree and emit modification events based on mtime changes."""
    if not os.path.exists(path):
        return

    if os.path.isfile(path):
        if _match_any(path, patterns) and not _match_ignore(path, ignore_patterns):
            mtime = os.path.getmtime(path)
            if path in last_mtimes:
                if mtime > last_mtimes[path]:
                    yield FileEvent(type="modified", path=path)
            last_mtimes[path] = mtime
        return

    for root, dirs, files in os.walk(path, topdown=True):
        if not recursive:
            dirs.clear()

        # Prune ignored directories
        dirs[:] = [d for d in dirs if not _match_ignore(os.path.join(root, d), ignore_patterns)]

        for fname in files:
            fpath = os.path.join(root, fname)
            if not _match_any(fpath, patterns):
                continue
            if _match_ignore(fpath, ignore_patterns):
                continue

            try:
                mtime = os.path.getmtime(fpath)
            except OSError:
                # File deleted between scan
                if fpath in last_mtimes:
                    del last_mtimes[fpath]
                    yield FileEvent(type="deleted", path=fpath)
                continue

            if fpath not in last_mtimes:
                yield FileEvent(type="created", path=fpath)
            elif mtime > last_mtimes[fpath]:
                yield FileEvent(type="modified", path=fpath)

            last_mtimes[fpath] = mtime


class _NativeWatcher:
    """Polling-based watcher. Cross-platform, no dependencies."""

    def __init__(
        self,
        path: str,
        patterns: Optional[list[str]] = None,
        ignore_patterns: Optional[list[str]] = None,
        recursive: bool = True,
        debounce_ms: int = 0,
        poll_interval: float = 1.0,
    ):
        self.path = path
        self.patterns = patterns or []
        self.ignore_patterns = ignore_patterns or []
        self.recursive = recursive
        self.debounce_ms = debounce_ms
        self.poll_interval = poll_interval
        self._last_mtimes: dict[str, float] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._queue: list[FileEvent] = []
        self._lock = threading.Lock()
        self._last_debounce = 0.0

    def _scan(self):
        for event in _native_walk(
            self.path, self.recursive, self.patterns, self.ignore_patterns, self._last_mtimes
        ):
            with self._lock:
                self._queue.append(event)
                self._last_debounce = time.time()

    def _loop(self):
        while self._running:
            time.sleep(self.poll_interval)
            self._scan()

    def __iter__(self):
        self._running = True

        # Initial scan
        self._scan()

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

        while self._running:
            time.sleep(0.05)  # Poll every 50ms for responsiveness

            with self._lock:
                if not self._queue:
                    continue

                # Debounce check
                if self.debounce_ms > 0:
                    age_ms = (time.time() - self._last_debounce) * 1000
                    if age_ms < self.debounce_ms:
                        continue

                events = list(self._queue)
                self._queue.clear()

            yield from events

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)


class _CoalescingWatcher:
    """Wraps a watcher and batches events over a time window."""

    def __init__(self, inner, window_ms: int = 1000):
        self._inner = inner
        self._window_ms = window_ms
        self._buffer: list[FileEvent] = []
        self._last_batch_time = 0.0

    def __iter__(self):
        for event in self._inner:
            self._buffer.append(event)
            self._last_batch_time = time.time()

            # Fire if window elapsed
            if (time.time() - self._last_batch_time) * 1000 >= self._window_ms:
                batch = list(self._buffer)
                self._buffer.clear()
                yield batch

        # Flush remaining
        if self._buffer:
            yield list(self._buffer)


class _ThrottleWatcher:
    """Rate-limits watcher events."""

    def __init__(self, inner, rate_ms: int = 1000):
        self._inner = inner
        self._rate_ms = rate_ms
        self._last_fire = 0.0

    def __iter__(self):
        for event in self._inner:
            now = time.time()
            if (now - self._last_fire) * 1000 >= self._rate_ms:
                self._last_fire = now
                yield event


# ── Main API ──────────────────────────────────────────────────────────────────

def watch(
    path: str,
    *,
    patterns: Optional[list[str]] = None,
    ignore: Optional[list[str]] = None,
    recursive: bool = True,
    debounce_ms: int = 0,
    use_polling: bool = False,
    poll_interval: float = 1.0,
) -> _NativeWatcher:
    """
    Watch a directory or file for changes.

    Args:
        path: Directory or file to watch
        patterns: Glob patterns to include (e.g. ["*.py", "*.js"])
        ignore: Glob patterns to exclude (e.g. ["test_*.py", "__pycache__/*"])
        recursive: Watch subdirectories
        debounce_ms: Collapse rapid-fire changes (wait this many ms after last change)
        use_polling: Always use polling (default: auto-detect)
        poll_interval: Seconds between polls when polling

    Returns:
        Iterator of FileEvent objects

    Example:
        for event in watch("src/", patterns=["*.py"], debounce_ms=500):
            print(f"{event.type}: {event.path}")
    """
    return _NativeWatcher(
        path=path,
        patterns=patterns,
        ignore_patterns=ignore,
        recursive=recursive,
        debounce_ms=debounce_ms,
        poll_interval=poll_interval,
    )


def ignore(*patterns: str) -> list[str]:
    """Helper to create ignore pattern list."""
    return list(patterns)


# ── Async watcher ─────────────────────────────────────────────────────────────

class AsyncWatcher:
    """Async file watcher using polling."""

    def __init__(
        self,
        path: str,
        *,
        patterns: Optional[list[str]] = None,
        ignore_patterns: Optional[list[str]] = None,
        recursive: bool = True,
        debounce_ms: int = 0,
        poll_interval: float = 1.0,
    ):
        self.path = path
        self.patterns = patterns or []
        self.ignore_patterns = ignore_patterns or []
        self.recursive = recursive
        self.debounce_ms = debounce_ms
        self.poll_interval = poll_interval
        self._last_mtimes: dict[str, float] = {}
        self._running = False

    async def _scan(self) -> list[FileEvent]:
        events = []
        for event in _native_walk(
            self.path, self.recursive, self.patterns, self.ignore_patterns, self._last_mtimes
        ):
            events.append(event)
        return events

    async def __aiter__(self):
        self._running = True

        # Initial scan
        await self._scan()

        debounce_buffer: list[FileEvent] = []
        last_debounce = 0.0

        while self._running:
            await asyncio.sleep(self.poll_interval)
            events = await self._scan()

            if not events:
                continue

            if self.debounce_ms > 0:
                debounce_buffer.extend(events)
                last_debounce = time.time()
                if (time.time() - last_debounce) * 1000 < self.debounce_ms:
                    continue
                batch = list(debounce_buffer)
                debounce_buffer.clear()
                for e in batch:
                    yield e
            else:
                for e in events:
                    yield e

    def stop(self):
        self._running = False
