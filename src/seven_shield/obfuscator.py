"""AST-based, dependency-free Python source obfuscation."""

from __future__ import annotations

import ast
import base64
import builtins
import keyword
import marshal
import random
import zlib
from dataclasses import dataclass


_RESERVED = {
    "__name__",
    "__file__",
    "__package__",
    "__spec__",
    "__loader__",
    "__cached__",
    "__builtins__",
    "self",
    "cls",
}
_HELPER_DECODE = "_ss_decode"
_HELPER_BUILTIN = "_ss_builtin"


def _confusable_name(rng: random.Random, used: set[str], length: int = 22) -> str:
    """Return a unique identifier composed only of visually similar glyphs."""
    while True:
        candidate = "".join(rng.choice("Il") for _ in range(length))
        if candidate not in used:
            used.add(candidate)
            return candidate


@dataclass(frozen=True, slots=True)
class ObfuscationOptions:
    """Select the transformations applied to a Python source file."""

    rename: bool = True
    encrypt: bool = True
    flatten: bool = True
    hide_builtins: bool = True
    hide_imports: bool = True
    hide_attrs: bool = True
    junk_code: bool = True
    seed: int | None = None


class _CandidateCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)

    def visit_arg(self, node: ast.arg) -> None:
        self.names.add(node.arg)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.names.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.names.add(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names.add(node.name)
        self.generic_visit(node)

    def visit_alias(self, node: ast.alias) -> None:
        self.names.add(node.asname or node.name.split(".")[0])


class _IdentifierRenamer(ast.NodeTransformer):
    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping

    def visit_Name(self, node: ast.Name) -> ast.Name:
        node.id = self.mapping.get(node.id, node.id)
        return node

    def visit_arg(self, node: ast.arg) -> ast.arg:
        node.arg = self.mapping.get(node.arg, node.arg)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        node.name = self.mapping.get(node.name, node.name)
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        node.name = self.mapping.get(node.name, node.name)
        return self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        node.name = self.mapping.get(node.name, node.name)
        return self.generic_visit(node)

    def visit_alias(self, node: ast.alias) -> ast.alias:
        binding = node.asname or node.name.split(".")[0]
        replacement = self.mapping.get(binding)
        if replacement:
            node.asname = replacement
        return node

    def visit_keyword(self, node: ast.keyword) -> ast.keyword:
        if node.arg is not None:
            node.arg = self.mapping.get(node.arg, node.arg)
        return self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> ast.Global:
        node.names = [self.mapping.get(name, name) for name in node.names]
        return node

    def visit_Nonlocal(self, node: ast.Nonlocal) -> ast.Nonlocal:
        node.names = [self.mapping.get(name, name) for name in node.names]
        return node


class _StringProtector(ast.NodeTransformer):
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.in_joined_string = False

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.JoinedStr:
        previous = self.in_joined_string
        self.in_joined_string = True
        self.generic_visit(node)
        self.in_joined_string = previous
        return node

    def _visit_body(self, body: list[ast.stmt]) -> list[ast.stmt]:
        start = 1 if body and _is_docstring(body[0]) else 0
        return body[:start] + [self.visit(statement) for statement in body[start:]]

    def visit_Module(self, node: ast.Module) -> ast.Module:
        node.body = self._visit_body(node.body)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        node.decorator_list = [self.visit(item) for item in node.decorator_list]
        node.args = self.visit(node.args)
        node.returns = self.visit(node.returns) if node.returns else None
        node.body = self._visit_body(node.body)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        return self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        node.decorator_list = [self.visit(item) for item in node.decorator_list]
        node.bases = [self.visit(item) for item in node.bases]
        node.keywords = [self.visit(item) for item in node.keywords]
        node.body = self._visit_body(node.body)
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.expr:
        if not isinstance(node.value, str) or self.in_joined_string:
            return node
        key = self.rng.randrange(1, 256)
        payload = bytes(byte ^ key for byte in node.value.encode("utf-8"))
        encoded = base64.b85encode(payload).decode("ascii")
        return ast.copy_location(
            ast.Call(
                func=ast.Name(id=_HELPER_DECODE, ctx=ast.Load()),
                args=[ast.Constant(encoded), ast.Constant(key)],
                keywords=[],
            ),
            node,
        )


class _ImportHider(ast.NodeTransformer):
    @staticmethod
    def _import_call(module: str, fromlist: tuple[str, ...] = ()) -> ast.Call:
        return ast.Call(
            func=ast.Name(id="__import__", ctx=ast.Load()),
            args=[ast.Constant(module)],
            keywords=[ast.keyword(arg="fromlist", value=ast.Constant(fromlist))] if fromlist else [],
        )

    def visit_Import(self, node: ast.Import) -> list[ast.stmt]:
        assignments: list[ast.stmt] = []
        for alias in node.names:
            binding = alias.asname or alias.name.split(".")[0]
            module = alias.name if alias.asname else alias.name.split(".")[0]
            assignments.append(
                ast.copy_location(
                    ast.Assign(
                        targets=[ast.Name(id=binding, ctx=ast.Store())],
                        value=self._import_call(module),
                    ),
                    node,
                )
            )
        return assignments

    def visit_ImportFrom(self, node: ast.ImportFrom) -> list[ast.stmt] | ast.ImportFrom:
        if node.module == "__future__" or node.level or node.module is None or any(alias.name == "*" for alias in node.names):
            return node
        assignments: list[ast.stmt] = []
        for alias in node.names:
            binding = alias.asname or alias.name
            imported = self._import_call(node.module, (alias.name,))
            value = ast.Call(
                func=ast.Name(id="getattr", ctx=ast.Load()),
                args=[imported, ast.Constant(alias.name)],
                keywords=[],
            )
            assignments.append(
                ast.copy_location(ast.Assign(targets=[ast.Name(id=binding, ctx=ast.Store())], value=value), node)
            )
        return assignments


class _BuiltinHider(ast.NodeTransformer):
    def __init__(self) -> None:
        self.builtin_names = set(dir(builtins)) - {"__import__"}

    def visit_Name(self, node: ast.Name) -> ast.expr:
        if isinstance(node.ctx, ast.Load) and node.id in self.builtin_names:
            return ast.copy_location(
                ast.Call(
                    func=ast.Name(id=_HELPER_BUILTIN, ctx=ast.Load()),
                    args=[ast.Constant(node.id)],
                    keywords=[],
                ),
                node,
            )
        return node


class _AttributeHider(ast.NodeTransformer):
    def visit_Attribute(self, node: ast.Attribute) -> ast.expr:
        node = self.generic_visit(node)
        if isinstance(node.ctx, ast.Load):
            return ast.copy_location(
                ast.Call(
                    func=ast.Name(id="getattr", ctx=ast.Load()),
                    args=[node.value, ast.Constant(node.attr)],
                    keywords=[],
                ),
                node,
            )
        return node


class _ControlFlowFlattener(ast.NodeTransformer):
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def _flatten(self, body: list[ast.stmt]) -> list[ast.stmt]:
        if len(body) < 2:
            return body
        prefix: list[ast.stmt] = []
        if _is_docstring(body[0]):
            prefix.append(body.pop(0))
        state_name = f"_ss_state_{self.rng.randrange(10_000, 99_999)}"
        order = list(range(len(body)))
        tokens = self.rng.sample(range(100_000, 999_999), len(body) + 1)
        branches: list[ast.stmt] = []
        for index in order:
            statements = [body[index]]
            if not isinstance(body[index], (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                statements.append(
                    ast.Assign(
                        targets=[ast.Name(id=state_name, ctx=ast.Store())],
                        value=ast.Constant(tokens[index + 1]),
                    )
                )
            branches.append(
                ast.If(
                    test=ast.Compare(
                        left=ast.Name(id=state_name, ctx=ast.Load()),
                        ops=[ast.Eq()],
                        comparators=[ast.Constant(tokens[index])],
                    ),
                    body=statements,
                    orelse=[],
                )
            )
        branches.append(
            ast.If(
                test=ast.Compare(
                    left=ast.Name(id=state_name, ctx=ast.Load()),
                    ops=[ast.Eq()],
                    comparators=[ast.Constant(tokens[-1])],
                ),
                body=[ast.Break()],
                orelse=[],
            )
        )
        return prefix + [
            ast.Assign(targets=[ast.Name(id=state_name, ctx=ast.Store())], value=ast.Constant(tokens[0])),
            ast.While(test=ast.Constant(True), body=branches, orelse=[]),
        ]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        node.body = self._flatten(node.body)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        self.generic_visit(node)
        node.body = self._flatten(node.body)
        return node


class _JunkInserter(ast.NodeTransformer):
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def _junk(self) -> ast.If:
        name = f"_ss_noise_{self.rng.randrange(10_000, 99_999)}"
        return ast.If(
            test=ast.Constant(False),
            body=[
                ast.Assign(
                    targets=[ast.Name(id=name, ctx=ast.Store())],
                    value=ast.BinOp(
                        left=ast.Constant(self.rng.randrange(100, 999)),
                        op=ast.BitXor(),
                        right=ast.Constant(self.rng.randrange(100, 999)),
                    ),
                )
            ],
            orelse=[],
        )

    def visit_Module(self, node: ast.Module) -> ast.Module:
        self.generic_visit(node)
        insertion = 1 if node.body and _is_docstring(node.body[0]) else 0
        node.body.insert(insertion, self._junk())
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        insertion = 1 if node.body and _is_docstring(node.body[0]) else 0
        node.body.insert(insertion, self._junk())
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        self.generic_visit(node)
        insertion = 1 if node.body and _is_docstring(node.body[0]) else 0
        node.body.insert(insertion, self._junk())
        return node


def _is_docstring(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


class Obfuscator:
    """Apply selected transformations and return executable Python source."""

    def obfuscate(self, source: str, options: ObfuscationOptions | None = None) -> str:
        """Obfuscate *source* according to *options*."""
        selected = options or ObfuscationOptions()
        tree = ast.parse(source)
        module_docstring = tree.body[0] if tree.body and _is_docstring(tree.body[0]) else None
        if module_docstring is not None:
            tree.body.pop(0)
        future_nodes = [
            statement
            for statement in tree.body
            if isinstance(statement, ast.ImportFrom) and statement.module == "__future__"
        ]
        tree.body = [statement for statement in tree.body if statement not in future_nodes]
        rng = random.Random(selected.seed)

        if selected.rename:
            collector = _CandidateCollector()
            collector.visit(tree)
            forbidden = set(keyword.kwlist) | _RESERVED
            names = sorted(name for name in collector.names if name not in forbidden and not name.startswith("__"))
            used_names = set(forbidden) | collector.names
            mapping = {name: _confusable_name(rng, used_names) for name in names}
            tree = _IdentifierRenamer(mapping).visit(tree)
        if selected.flatten:
            tree = _ControlFlowFlattener(rng).visit(tree)
        if selected.hide_imports:
            tree = _ImportHider().visit(tree)
        if selected.hide_attrs:
            tree = _AttributeHider().visit(tree)
        if selected.hide_builtins:
            tree = _BuiltinHider().visit(tree)
        if selected.junk_code:
            tree = _JunkInserter(rng).visit(tree)
        if selected.encrypt:
            tree = _StringProtector(rng).visit(tree)

        ast.fix_missing_locations(tree)
        future_source = "\n".join(ast.unparse(statement) for statement in future_nodes)
        if future_source:
            future_source += "\n"
        docstring_source = f"{ast.unparse(module_docstring)}\n" if module_docstring is not None else ""
        preamble = self._preamble(selected)
        output = future_source + docstring_source + preamble + ast.unparse(tree) + "\n"
        compile(output, "<obfuscated>", "exec")
        if selected.encrypt:
            output = self._pack(output, rng, selected.junk_code)
            compile(output, "<seven-shield-loader>", "exec")
        return output

    @staticmethod
    def _pack(source: str, rng: random.Random, include_decoy: bool) -> str:
        """Compile, compress and mask source behind a small executable loader."""
        code = compile(source, "<seven-shield>", "exec")
        compressed = zlib.compress(marshal.dumps(code), level=9)
        key = bytes(rng.randrange(1, 256) for _ in range(32))
        masked = bytes(value ^ key[index % len(key)] for index, value in enumerate(compressed))
        payload = base64.b85encode(masked)
        used: set[str] = set()
        payload_name = _confusable_name(rng, used, 28)
        key_name = _confusable_name(rng, used, 28)
        data_name = _confusable_name(rng, used, 28)
        index_name = _confusable_name(rng, used, 18)
        value_name = _confusable_name(rng, used, 18)
        lines = [
            "__obfuscated_by__ = 'Seven Shield'",
            f"{payload_name} = {payload!r}",
            f"{key_name} = {key!r}",
        ]
        if include_decoy:
            decoy_name = _confusable_name(rng, used, 24)
            left = rng.randrange(100_000, 999_999)
            right = rng.randrange(100_000, 999_999)
            lines.extend(
                [
                    f"{decoy_name} = ({left} ^ {right}) & 0xffff",
                    f"if {decoy_name} == -1:",
                    f"    {payload_name} = {payload_name}[::-1]",
                ]
            )
        lines.extend(
            [
                f"{data_name} = __import__('base64').b85decode({payload_name})",
                "getattr(__import__('builtins'), 'exec')(",
                "    __import__('marshal').loads(",
                "        __import__('zlib').decompress(",
                f"            bytes({value_name} ^ {key_name}[{index_name} % len({key_name})]",
                f"                  for {index_name}, {value_name} in enumerate({data_name}))",
                "        )",
                "    )",
                ")",
            ]
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _preamble(options: ObfuscationOptions) -> str:
        lines = ["# Generated by Seven Shield. Keep the original source."]
        if options.encrypt:
            lines.extend(
                [
                    "import base64 as _ss_b64",
                    f"def {_HELPER_DECODE}(data, key):",
                    "    raw = _ss_b64.b85decode(data.encode('ascii'))",
                    "    return bytes(byte ^ key for byte in raw).decode('utf-8')",
                ]
            )
        if options.hide_builtins:
            lines.extend(
                [
                    "import builtins as _ss_builtins",
                    f"def {_HELPER_BUILTIN}(name):",
                    "    return getattr(_ss_builtins, name)",
                ]
            )
        return "\n".join(lines) + "\n"
