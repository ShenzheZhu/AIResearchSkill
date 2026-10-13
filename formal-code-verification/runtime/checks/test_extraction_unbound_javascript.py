#!/usr/bin/env python3
"""Real grammars retain unbound callable identities and original source slices."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import executor
from fm_agent_core import languages, state


class ExtractionUnboundJavascriptTest(unittest.TestCase):
    def extract(self, target, suffix, source):
        path = target / ("api" + suffix)
        path.write_text(source, encoding="utf-8")
        _, backend = languages.function_spans(path)
        if backend == "tree-sitter-unavailable":
            self.skipTest(f"real Tree-sitter grammar unavailable for {suffix}")
        self.assertEqual(backend, "tree-sitter")
        result = executor.extract(target, [])
        manifest = state.read_json(target / "fm_agent/extraction_manifest.json", {})["functions"]
        self.assertEqual({item["function_id"] for item in manifest}, {item["id"] for item in result["index"]["functions"]})
        self.assertEqual(len({item["artifact"] for item in manifest}), len(manifest))
        lines = source.splitlines(keepends=True)
        for item in manifest:
            self.assertEqual(item["source_path"], path.name)
            self.assertEqual(item["extraction_backend"], "tree-sitter")
            artifact = target / "fm_agent/extracted_functions" / item["artifact"]
            self.assertEqual(artifact.read_text(), "".join(lines[item["line_start"] - 1:item["line_end"]]))
        return manifest

    def test_multiline_callbacks_iife_defaults_and_inner_named_coverage(self):
        source = """register(
  value => {
    function helper(value) {
      return value + 1;
    }
    const bound = function internal(value) { return value; };
    use(function named(value) { return bound(value); });
    return helper(value);
  }
);
(() => {
  function inside() { return 1; }
})();
export default function(value) { return value; };
"""
        expected = {
            "arrow_function@2:3": (2, 9), "helper": (3, 5),
            "bound": (6, 6), "named": (7, 7),
            "arrow_function@11:2": (11, 13), "inside": (12, 12),
            "function_expression@14:16": (14, 14),
        }
        for suffix in (".js", ".ts", ".tsx"):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as temporary:
                manifest = self.extract(Path(temporary).resolve(), suffix, source)
                self.assertEqual({item["name"]: (item["line_start"], item["line_end"]) for item in manifest}, expected)

    def test_same_line_callback_collisions_and_stable_byte_columns(self):
        source = 'const label = "流程"; use(value => value); use(function*() { yield 1; }); use(value => value);\n'
        expected = {
            "arrow_function@1:" + str(source.encode().index(b"value =>") + 1),
            "generator_function@1:" + str(source.encode().index(b"function*") + 1),
            "arrow_function@1:" + str(source.encode().rindex(b"value =>") + 1),
        }
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary).resolve()
            first = self.extract(target, ".js", source)
            second = self.extract(target, ".js", source)
            self.assertEqual({item["name"] for item in first}, expected)
            self.assertEqual(first, second)

    def test_nested_named_callbacks_keep_names_and_direct_binding_has_one_identity(self):
        source = """function run() {
  use(function callback() {
    use(function* generator() { yield 1; });
    use(value => value);
  });
  const bound = function alias() { return 1; };
}
"""
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.extract(Path(temporary).resolve(), ".js", source)
            self.assertEqual({item["name"] for item in manifest}, {"run", "callback", "generator", "bound"})

    def test_typescript_annotations_and_tsx_callbacks_use_actual_grammar(self):
        for suffix, source in ((".ts", "use((value: number): number => value + 1);\n"), (".tsx", "use((value: string) => <span>{value}</span>);\n")):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as temporary:
                manifest = self.extract(Path(temporary).resolve(), suffix, source)
                self.assertEqual([item["name"] for item in manifest], ["arrow_function@1:5"])


if __name__ == "__main__":
    unittest.main()
