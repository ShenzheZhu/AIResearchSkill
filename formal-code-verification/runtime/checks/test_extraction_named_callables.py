#!/usr/bin/env python3
"""Grammar-shaped seams exercise the existing extractor without installing parsers."""
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import executor
from fm_agent_core import languages


class Node:
    def __init__(self, kind, start, end, children=(), fields=None):
        self.type = kind
        self.start_byte, self.end_byte = start, end
        self.start_point, self.end_point = (0, start), (0, end)
        self.children = self.named_children = list(children)
        self.fields = fields or {}
        self.parent = None
        self.has_error = False
        for child in children:
            child.parent = self

    def child_by_field_name(self, name):
        return self.fields.get(name)


class ExtractionNamedCallablesTest(unittest.TestCase):
    def extract(self, suffix, source, root):
        parser = SimpleNamespace(parse=lambda content: SimpleNamespace(root_node=root))
        grammar = SimpleNamespace(get_parser=lambda name: parser)
        with tempfile.TemporaryDirectory() as temporary, patch.dict(sys.modules, {"tree_sitter_languages": grammar}):
            target = Path(temporary)
            path = target / ("api" + suffix)
            path.write_text(source)
            return executor.extract(target, [])

    def test_javascript_and_typescript_direct_callable_initializers(self):
        for suffix in (".js", ".ts", ".tsx"):
            for kind in ("arrow_function", "function_expression", "generator_function"):
                with self.subTest(suffix=suffix, kind=kind):
                    initializers = {"arrow_function": "(value) => value", "function_expression": "function(value) { return value; }", "generator_function": "function*(value) { yield value; }"}
                    source = "export const callable = " + initializers[kind] + ";"
                    start = source.index("callable")
                    name = Node("identifier", start, start + len("callable"))
                    value = Node(kind, source.index("= ") + 2, len(source) - 1)
                    declaration = Node("variable_declarator", start, len(source) - 1, [name, value], {"name": name, "value": value})
                    lexical = Node("lexical_declaration", source.index("const"), len(source), [declaration])
                    export = Node("export_statement", 0, len(source), [lexical])
                    out = self.extract(suffix, source, Node("program", 0, len(source), [export]))
                    self.assertEqual(out["function_count"], 1)
                    self.assertEqual(out["index"]["functions"][0]["id"], "api" + suffix + "::callable")

    def test_go_single_var_spec_binds_function_literal(self):
        source = "var IsValid = func(value int) bool { return value > 0 }"
        start = source.index("IsValid")
        name = Node("identifier", start, start + len("IsValid"))
        literal = Node("func_literal", source.index("func"), len(source))
        values = Node("expression_list", literal.start_byte, len(source), [literal])
        declaration = Node("var_spec", start, len(source), [name, values], {"name": name, "value": values})
        out = self.extract(".go", source, Node("source_file", 0, len(source), [declaration]))
        self.assertEqual(out["function_count"], 1)
        self.assertEqual(out["index"]["functions"][0]["id"], "api.go::IsValid")

    def test_unicode_names_are_retained_and_anonymous_defaults_fail(self):
        for suffix, source, name_text in ((".js", "export function 流程(value) { return value + 1; }", "流程"), (".js", "export function $流程(value) { return value + 1; }", "$流程"), (".go", "func ΔCount(value int) int { return value + 1 }", "ΔCount")):
            with self.subTest(suffix=suffix):
                start = source.encode().index(name_text.encode())
                name = Node("identifier", start, start + len(name_text.encode()))
                declaration = Node("function_declaration", 0, len(source.encode()), [name], {"name": name})
                out = self.extract(suffix, source, Node("program", 0, len(source.encode()), [declaration]))
                self.assertEqual(out["index"]["functions"][0]["id"], "api" + suffix + "::" + name_text)
        source = "export default function(value) { return value + 1; }"
        declaration = Node("function_declaration", source.index("function"), len(source))
        with self.assertRaisesRegex(ValueError, "Unsupported callable declaration without a name"):
            self.extract(".js", source, Node("program", 0, len(source), [declaration]))

    def test_python_named_lambdas_use_tree_and_native_ast(self):
        source = "check = lambda value: value > 0"
        name = Node("identifier", 0, len("check"))
        value = Node("lambda", source.index("lambda"), len(source))
        assignment = Node("assignment", 0, len(source), [name, value], {"left": name, "right": value})
        out = self.extract(".py", source, Node("module", 0, len(source), [assignment]))
        self.assertEqual(out["index"]["functions"][0]["id"], "api.py::check")
        with tempfile.TemporaryDirectory() as temporary, patch.object(languages, "_tree_sitter_spans", return_value=None):
            path = Path(temporary) / "api.py"
            path.write_text("def count(value):\n    return value + 1\ncheck = lambda value: value > 0\n")
            self.assertEqual(languages.function_spans(path), ([("count", 1, 2), ("check", 3, 3)], "python-ast"))
            path.write_text("def count():\n    return list(map(lambda value: value + 1, [1]))\n")
            self.assertEqual(languages.function_spans(path), ([("count", 1, 2)], "python-ast"))
            path.write_text("def count(value):\n    return value + 1\nregister(lambda value: value > 0)\n")
            with self.assertRaisesRegex(ValueError, "Unsupported unbound callable"):
                languages.function_spans(path)

    @unittest.skipUnless(shutil.which("clang") and shutil.which("clang++"), "Clang AST capability is unavailable")
    def test_c_family_unnamed_tree_declarator_reuses_clang(self):
        source = "int count(int value) { return value + 1; }"
        for suffix in (".c", ".cpp"):
            with self.subTest(suffix=suffix):
                declarator = Node("function_declarator", source.index("count"), source.index("{"))
                declaration = Node("function_definition", 0, len(source), [declarator], {"declarator": declarator})
                out = self.extract(suffix, source, Node("translation_unit", 0, len(source), [declaration]))
                self.assertEqual(out["index"]["functions"][0]["id"], "api" + suffix + "::count")

    def test_top_level_callbacks_fail_but_nested_callbacks_remain_covered(self):
        for suffix, kind, source in ((".js", "arrow_function", "function run() { use(value => value + 1); }"), (".go", "func_literal", "func Run() { Use(func() {}) }")):
            with self.subTest(suffix=suffix):
                top_source = "function run() { return 1; } use(value => value + 1);" if suffix == ".js" else "package api; func Run() int { return 1 }; var result = Use(func() {})"
                callback_start = top_source.index("value =>") if suffix == ".js" else top_source.index("func()")
                callback = Node(kind, callback_start, len(top_source) - 2)
                name_text = "run" if suffix == ".js" else "Run"
                start = top_source.index(name_text)
                name = Node("identifier", start, start + len(name_text))
                declaration_end = top_source.index("}") + 1
                declaration = Node("function_declaration", top_source.index("function" if suffix == ".js" else "func Run"), declaration_end, [name], {"name": name})
                top_level = Node("call_expression", callback_start - 4, len(top_source), [callback])
                with self.assertRaisesRegex(ValueError, "Unsupported unbound callable"):
                    self.extract(suffix, top_source, Node("program", 0, len(top_source), [declaration, top_level]))
                callback_start = source.index("value =>") if suffix == ".js" else source.index("func()")
                callback = Node(kind, callback_start, len(source) - 3)
                start = source.index(name_text)
                name = Node("identifier", start, start + len(name_text))
                declaration = Node("function_declaration", 0, len(source), [name, callback], {"name": name})
                out = self.extract(suffix, source, Node("program", 0, len(source), [declaration]))
                self.assertEqual(out["function_count"], 1)
                self.assertEqual(out["index"]["functions"][0]["id"], "api" + suffix + "::" + name_text)

    def test_ambiguous_go_and_destructured_javascript_bindings_fail(self):
        source = "var a, b = func() int { return 1 }, func() int { return 2 }"
        name = Node("identifier", 4, 5)
        other = Node("identifier", 7, 8)
        first = source.index("func")
        second = source.index("func", first + 1)
        literals = [Node("func_literal", first, second - 2), Node("func_literal", second, len(source))]
        values = Node("expression_list", first, len(source), literals)
        declaration = Node("var_spec", 4, len(source), [name, other, values], {"name": name, "value": values})
        with self.assertRaisesRegex(ValueError, "Unsupported Go callable binding"):
            self.extract(".go", source, Node("source_file", 0, len(source), [declaration]))
        name = Node("array_pattern", 0, 3)
        literal = Node("arrow_function", 5, 10)
        declaration = Node("variable_declarator", 0, 10, [name, literal], {"name": name, "value": literal})
        with self.assertRaisesRegex(ValueError, "Unsupported callable binding"):
            self.extract(".js", "[a] = x", Node("program", 0, 10, [declaration]))


if __name__ == "__main__":
    unittest.main()
