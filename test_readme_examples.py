"""Every python block in the README must parse, and must import real names.

Added 2026-11-04. The README's first example was
``from tiny_watch import watch, ignore, debounce`` -- there is no ``debounce``
symbol. Debouncing is the ``debounce_ms`` argument to ``watch()``. Anyone
copy-pasting the README got an ImportError on a library that works fine.
"""
import io
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

README = pathlib.Path(__file__).resolve().parent / "README.md"
BLOCK = re.compile(r"```python\n(.*?)```", re.S)


def _blocks():
    text = io.open(README, encoding="utf-8").read()
    return BLOCK.findall(text)


def test_readme_has_python_examples():
    assert _blocks(), "the README should carry at least one python example"


@pytest.mark.parametrize("block", _blocks())
def test_readme_example_parses(block):
    try:
        compile(block, "README.md", "exec")
    except SyntaxError as exc:
        pytest.fail(f"README example does not parse: {exc.msg} (line {exc.lineno})")


def test_readme_imports_only_real_symbols():
    """Every ``from tiny_watch import ...`` in the README must name a real symbol."""
    import tiny_watch

    text = io.open(README, encoding="utf-8").read()
    imported = set()
    for match in re.finditer(r"from tiny_watch import ([^\n]+)", text):
        for name in match.group(1).split(","):
            name = name.strip()
            if name:
                imported.add(name)
    missing = {n for n in imported if not hasattr(tiny_watch, n)}
    assert not missing, f"README imports names that do not exist: {sorted(missing)}"


def test_debounce_is_an_argument_not_a_symbol():
    import tiny_watch

    assert not hasattr(tiny_watch, "debounce"), (
        "debounce is the debounce_ms argument to watch(), not a module symbol"
    )
    import inspect

    assert "debounce_ms" in inspect.signature(tiny_watch.watch).parameters
