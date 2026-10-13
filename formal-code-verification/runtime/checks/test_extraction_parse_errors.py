#!/usr/bin/env python3
"""A parse failure cannot disappear behind an extracted sibling function."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import executor
from fm_agent_core import languages, state


class ExtractionParseErrorsTest(unittest.TestCase):
    def test_invalid_python_sibling_rejects_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            (target / "valid.py").write_text("def count(value):\n    return value + 1\n")
            (target / "broken.py").write_text("def broken(:\n    return 1\n")
            with patch.object(languages, "_tree_sitter_spans", return_value=None):
                with self.assertRaisesRegex(ValueError, "Source parsing failed: broken.py"):
                    executor.extract(target, [])
            self.assertFalse((target / "fm_agent/extraction_manifest.json").exists())

    def test_tree_sitter_error_rejects_extraction(self):
        parser = SimpleNamespace(parse=lambda source: SimpleNamespace(root_node=SimpleNamespace(has_error=True)))
        grammar = SimpleNamespace(get_parser=lambda name: parser)
        with tempfile.TemporaryDirectory() as temporary, patch.dict(sys.modules, {"tree_sitter_languages": grammar}):
            target = Path(temporary)
            (target / "broken.go").write_text("package api\nfunc Broken( {}\n")
            with self.assertRaisesRegex(ValueError, "Source parsing failed: broken.go"):
                executor.extract(target, [])

    def test_failed_rerun_does_not_leave_a_ready_index(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(languages, "_tree_sitter_spans", return_value=None):
            target = Path(temporary)
            source = target / "api.py"
            source.write_text("def count(value):\n    return value + 1\n")
            executor.extract(target, [])
            self.assertEqual(len(state.scoped_functions(target, [])), 1)
            source.write_text("def count(:\n    return 1\n")
            with self.assertRaisesRegex(ValueError, "Source parsing failed: api.py"):
                executor.extract(target, [])
            self.assertEqual(state.scoped_functions(target, []), [])
            self.assertFalse((target / "fm_agent/extraction_manifest.json").exists())
            self.assertFalse((target / "fm_agent/fm_agent_file_list.json").exists())

    def test_tsx_selects_its_grammar(self):
        selected = []
        parser = SimpleNamespace(parse=lambda source: SimpleNamespace(root_node=SimpleNamespace(type="program", has_error=False, children=[])))
        grammar = SimpleNamespace(get_parser=lambda name: selected.append(name) or parser)
        with tempfile.TemporaryDirectory() as temporary, patch.dict(sys.modules, {"tree_sitter_languages": grammar}):
            source = Path(temporary) / "view.tsx"
            source.write_text("export const View = () => <div />;\n")
            self.assertEqual(languages.function_spans(source), ([], "tree-sitter"))
        self.assertEqual(selected, ["tsx"])

    def test_missing_parser_still_rejects_extraction(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(languages, "_tree_sitter_spans", return_value=None):
            target = Path(temporary)
            (target / "api.ts").write_text("export function count() { return 1; }\n")
            with self.assertRaisesRegex(ValueError, "Tree-sitter is required"):
                executor.extract(target, [])


if __name__ == "__main__":
    unittest.main()
