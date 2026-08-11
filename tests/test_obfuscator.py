"""Behavioral tests for the obfuscation pipeline."""

from __future__ import annotations

import contextlib
import io
import unittest

from seven_shield.obfuscator import ObfuscationOptions, Obfuscator


SAMPLE = '''
import math
import hashlib

def summarize(words):
    total = sum(len(w) for w in words)
    longest = max(words, key=len)
    sig = hashlib.md5("".join(words).encode()).hexdigest()
    return total, longest, sig[:8]

words = ["python", "protect", "deploy"]
count, longest, sig = summarize(words)
print("total:", count, "longest:", longest, "pi:", round(math.pi, 3), sig)
'''

UNICODE_SAMPLE = '''
"""Documentazione preservata."""
def greet(name="mondo"):
    """Saluto pubblico."""
    return f"Ciao, {name}: città è più bella"
print(greet())
'''


def _run(source: str) -> str:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        exec(compile(source, "<test>", "exec"), {"__name__": "__main__"})
    return stream.getvalue()


class TestObfuscator(unittest.TestCase):
    def test_each_layer_preserves_behavior(self) -> None:
        fields = ["rename", "encrypt", "flatten", "hide_builtins", "hide_imports", "hide_attrs", "junk_code"]
        for field in fields:
            with self.subTest(field=field):
                values = {name: False for name in fields}
                values[field] = True
                protected = Obfuscator().obfuscate(SAMPLE, ObfuscationOptions(**values, seed=7))
                self.assertEqual(_run(protected), _run(SAMPLE))

    def test_all_layers_preserve_behavior(self) -> None:
        protected = Obfuscator().obfuscate(SAMPLE, ObfuscationOptions(seed=42))
        self.assertEqual(_run(protected), _run(SAMPLE))
        self.assertNotIn('"python"', protected)
        self.assertNotIn("import math", protected)
        self.assertIn("b85decode", protected)
        self.assertNotIn("summarize", protected)

    def test_invalid_python_is_rejected(self) -> None:
        with self.assertRaises(SyntaxError):
            Obfuscator().obfuscate("def broken(:")

    def test_unicode_and_docstrings_are_preserved(self) -> None:
        namespace: dict[str, object] = {"__name__": "protected"}
        protected = Obfuscator().obfuscate(UNICODE_SAMPLE, ObfuscationOptions(seed=9))
        exec(compile(protected, "<test>", "exec"), namespace)
        self.assertEqual(namespace["__doc__"], "Documentazione preservata.")

    def test_future_import_remains_first(self) -> None:
        source = "from __future__ import annotations\nvalue: list[str] = []\n"
        protected = Obfuscator().obfuscate(source, ObfuscationOptions(seed=3))
        compile(protected, "<test>", "exec")
        self.assertEqual(_run(protected), _run(source))

    def test_aggressive_output_changes_with_seed(self) -> None:
        first = Obfuscator().obfuscate('print("Ciao Mondo!")', ObfuscationOptions(seed=1))
        second = Obfuscator().obfuscate('print("Ciao Mondo!")', ObfuscationOptions(seed=2))
        self.assertNotEqual(first, second)
        self.assertNotIn("Ciao Mondo!", first)
        self.assertTrue(all(character in "Il" for character in first.splitlines()[1].split(" = ")[0]))


if __name__ == "__main__":
    unittest.main()
