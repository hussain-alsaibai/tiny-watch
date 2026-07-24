# tiny-watch

> Zero-dependency file watcher with debounce, coalescing, and intelligent filtering. One file. Built for auto-reload in dev servers, build pipelines, and AI agent file monitoring.

```bash
pip install tiny-watch
```

## Why?

You need to watch files and react to changes. `watchdog` is 40MB of dependencies. `tiny-watch` does the same in one file:

```python
from tiny_watch import watch, ignore, debounce

# Watch a directory
for path in watch("src/"):
    print(f"Changed: {path}")

# With filtering
for path in watch(".", patterns=["*.py", "*.json"], ignore=["test_*.py", ".git/*"]):
    rebuild()

# With debounce (wait 300ms for burst of changes)
for path in watch("src/", debounce_ms=300):
    run_tests()

# With coalescing (collect all changes, fire once)
for changes in watch("src/").coalesce():
    print(f"Batch: {len(changes)} files changed")
    rebuild()
```

## Features

- **Cross-platform** — Uses `select` on Linux, FSEvents on macOS, INotify on Windows via stdlib
- **Debounce** — Collapse rapid-fire changes into single events
- **Coalesce** — Collect changes over a window, fire with full batch
- **Glob patterns** — Include/exclude with `*.py`, `src/**/*.js`, etc.
- **Recursive** — Watch directories recursively
- **Throttle** — Rate-limit handler invocations
- **Async** — Full `async` iteration support
- **No dependencies** — Pure Python stdlib

## Installation

```bash
pip install tiny-watch
```

Or copy `tiny_watch.py` into your project. One file.

## Quick Start

### Basic Watch

```python
from tiny_watch import watch

# Watch current directory
for event in watch("."):
    print(f"{event.type}: {event.path}")

# Watch specific patterns
for event in watch("src/", patterns=["*.py"]):
    print(f"Python changed: {event.path}")
```

### Debounce (Collapse Rapid Changes)

```python
from tiny_watch import watch

# Wait 500ms after last change before firing
for event in watch("src/", debounce_ms=500):
    run_tests()  # runs ONCE after editing stops
```

### Coalesce (Batch Changes)

```python
from tiny_watch import watch

# Collect all changes over 2 seconds, then fire with full list
for events in watch("src/").coalesce(window_ms=2000):
    print(f"{len(events)} files changed")
    for e in events:
        print(f"  {e.type}: {e.path}")
```

### Filtering

```python
from tiny_watch import watch, ignore

# Only Python files
for e in watch("src/", patterns=["*.py"]):
    print(e.path)

# Exclude test files and node_modules
for e in watch(".", ignore=["test_*.py", "node_modules/*", "__pycache__/*"]):
    print(e.path)

# Combine
for e in watch("src/", patterns=["*.py", "*.js"], ignore=["test_*.py"]):
    print(e.path)
```

### Async Iteration

```python
import asyncio
from tiny_watch import AsyncWatcher

async def main():
    watcher = AsyncWatcher("src/", patterns=["*.py"])
    async for event in watcher:
        await run_tests(event.path)

asyncio.run(main())
```

### With Polling (Cross-Platform Fallback)

```python
from tiny_watch import watch

# Force polling if native events aren't available
for event in watch("src/", use_polling=True, poll_interval=1.0):
    print(f"Changed: {event.path}")
```

## API Reference

### `watch(path, *, patterns=None, ignore=None, recursive=True, debounce_ms=0, use_polling=False, poll_interval=1.0)`

Create a watcher iterator.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | str | — | Directory or file to watch |
| `patterns` | list[str] | None | Glob patterns to include |
| `ignore` | list[str] | None | Glob patterns to exclude |
| `recursive` | bool | True | Watch subdirectories |
| `debounce_ms` | int | 0 | Collapse changes within window |
| `use_polling` | bool | False | Force polling mode |
| `poll_interval` | float | 1.0 | Seconds between polls |

**Returns:** `Watcher` iterator yielding `FileEvent` objects

### `Watcher.coalesce(window_ms=1000)`

Batch changes over a time window.

```python
for events in watch("src/").coalesce(window_ms=2000):
    # events is a list of FileEvent
    rebuild(events)
```

### `Watcher.throttle(rate_ms=1000)`

Rate-limit handler invocations.

```python
for event in watch("src/").throttle(rate_ms=2000):
    log(event)  # at most once per 2 seconds
```

### `FileEvent`

Represents a file system event.

| Attribute | Type | Description |
|-----------|------|-------------|
| `type` | str | `"created"`, `"modified"`, `"deleted"`, `"renamed"` |
| `path` | str | Full path to the file |
| `src_path` | str | Original path (for renames) |
| `dst_path` | str | New path (for renames) |
| `timestamp` | float | Unix timestamp of event |

### `ignore(*patterns)`

Filter helper for exclude patterns.

```python
from tiny_watch import watch, ignore

for event in watch(".", ignore=[
    "*.pyc",
    "__pycache__/*",
    ".git/*",
    "node_modules/*",
    ".venv/*",
]):
    process(event)
```

## Real-World Examples

### Auto-Restart Dev Server

```python
import subprocess
import sys
from tiny_watch import watch

def restart():
    proc.terminate()
    proc = subprocess.Popen([sys.executable, "server.py"])

proc = subprocess.Popen([sys.executable, "server.py"])

for event in watch("src/", debounce_ms=500):
    print(f"Restarting... ({event.path})")
    restart()
```

### Build Pipeline

```python
from tiny_watch import watch

def build():
    subprocess.run(["npm", "run", "build"])

# Watch src, debounce, rebuild
for event in watch("src/", patterns=["*.ts", "*.tsx"], debounce_ms=1000):
    build()
```

### AI Agent File Monitor

```python
from tiny_watch import watch

# Watch for code changes, trigger AI review
for event in watch(".", patterns=["*.py", "*.js", "*.ts"]):
    if event.type == "modified":
        queue_ai_review(event.path)
```

## License

MIT — do whatever you want.
