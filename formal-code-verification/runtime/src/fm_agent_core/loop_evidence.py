"""Parser-grounded loop obligations; these validate evidence, not its truth."""
from __future__ import annotations

import ast
from pathlib import Path
import textwrap

from .languages import profile_for_path, _tree_sitter_language


def inventory(path: Path) -> dict:
    source = path.read_text(encoding="utf-8", errors="replace")
    loops = []
    normalized = textwrap.dedent(source)
    if path.suffix.lower() == ".py":
        try:
            tree = ast.parse(normalized)
        except SyntaxError as exc:
            return {"loops": [], "gap": f"loop parsing failed: {exc.msg}"}

        def visit(node, active=(), inside_callable=False):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                if inside_callable:
                    # Nested definitions evaluate their signature/decorators in the owner.
                    for field, value in ast.iter_fields(node):
                        if field != "body":
                            for child in value if isinstance(value, list) else [value]:
                                if isinstance(child, ast.AST):
                                    visit(child, active, True)
                else:
                    for child in node.body if isinstance(node.body, list) else [node.body]:
                        visit(child, active, True)
                return
            if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                loop = {"loop_id": f"loop-{len(loops) + 1:03d}", "statement": ast.get_source_segment(normalized, node), "abrupt_exits": []}
                loops.append(loop)
                active = (*active, loop)
            if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                for ordinal, generator in enumerate(node.generators, 1):
                    loops.append({"loop_id": f"loop-{len(loops) + 1:03d}", "statement": ast.get_source_segment(normalized, node), "generator_index": ordinal, "asynchronous": bool(generator.is_async), "abrupt_exits": []})
            if isinstance(node, (ast.Break, ast.Continue, ast.Return, ast.Raise)):
                for loop in active if isinstance(node, (ast.Return, ast.Raise)) else active[-1:]:
                    loop["abrupt_exits"].append({"exit_id": f"exit-{len(loop['abrupt_exits']) + 1:03d}", "statement": ast.get_source_segment(normalized, node)})
            for child in ast.iter_child_nodes(node):
                visit(child, active, inside_callable)

        visit(tree)
        return {"loops": loops, "gap": None}
    profile = profile_for_path(path)
    if profile is None or not profile.treesitter_languages:
        return {"loops": [], "gap": "loop parser unavailable for this language"}
    parser = None
    grammars = ("tsx",) if path.suffix.lower() == ".tsx" else profile.treesitter_languages
    try:
        from tree_sitter_languages import get_parser
    except ImportError:
        get_parser = None
    for name in grammars:
        if get_parser is not None:
            try:
                parser = get_parser(name)
                break
            except Exception:
                pass
        language = _tree_sitter_language(name)
        if language is not None:
            try:
                import tree_sitter
                parser = tree_sitter.Parser()
                try:
                    parser.language = language
                except (AttributeError, TypeError):
                    parser.set_language(language)
                break
            except Exception:
                parser = None
    if parser is None:
        return {"loops": [], "gap": "loop parser unavailable for this language"}
    encoded = source.encode()
    tree = parser.parse(encoded)
    # Extracted methods may require their language's enclosing class grammar.
    if tree.root_node.has_error and profile.key in {"javascript", "typescript", "java"}:
        encoded = b"class FM {\n" + encoded + b"\n}"
        tree = parser.parse(encoded)
    if tree.root_node.has_error:
        return {"loops": [], "gap": "loop parsing failed for the extracted source"}
    loop_types = {"for_statement", "for_in_statement", "for_of_statement", "for_range_loop", "enhanced_for_statement", "while_statement", "do_statement", "for_expression", "while_expression", "loop_expression"}
    abrupt_types = {"break_statement", "continue_statement", "return_statement", "throw_statement", "break_expression", "continue_expression", "return_expression"}
    callable_types = {"function_definition", "function_declaration", "function_item", "method_definition", "method_declaration", "arrow_function", "function_expression", "generator_function", "generator_function_declaration", "func_literal", "closure_expression", "lambda_expression"}
    switch_types = {"switch_statement", "expression_switch_statement", "type_switch_statement", "select_statement"}
    label_types = {"label_name", "statement_identifier", "label", "lifetime"}
    gaps = []

    def label(node):
        child = node.child_by_field_name("label") or next((child for child in node.named_children if child.type in label_types), None)
        return encoded[child.start_byte:child.end_byte].decode().strip("': ") if child is not None else None

    def visit(node, active=(), breakables=(), labels=(), inside_callable=False):
        if node.type in callable_types:
            if inside_callable:
                return
            inside_callable = True
        if node.type == "labeled_statement":
            name = label(node)
            if name:
                labels = (*labels, (name, len(active)))
        if node.type in loop_types:
            name = label(node)
            if name:
                labels = (*labels, (name, len(active)))
            loop = {"loop_id": f"loop-{len(loops) + 1:03d}", "statement": encoded[node.start_byte:node.end_byte].decode(), "abrupt_exits": []}
            loops.append(loop)
            active = (*active, loop)
            breakables = (*breakables, loop)
        elif node.type in switch_types:
            breakables = (*breakables, None)
        if node.type == "goto_statement" and active:
            gaps.append("loop exit ownership for goto is unavailable")
        if node.type in abrupt_types:
            name = label(node)
            if name:
                target = next((start for candidate, start in reversed(labels) if candidate == name), None)
                if target is None:
                    gaps.append("labeled loop exit target is unavailable")
                    exited = ()
                else:
                    exited = active[target:]
            elif node.type in {"return_statement", "throw_statement", "return_expression"}:
                exited = active
            elif node.type in {"continue_statement", "continue_expression"}:
                exited = active[-1:]
            else:
                exited = (breakables[-1],) if breakables and breakables[-1] is not None else ()
            for loop in exited:
                loop["abrupt_exits"].append({"exit_id": f"exit-{len(loop['abrupt_exits']) + 1:03d}", "statement": encoded[node.start_byte:node.end_byte].decode()})
        for child in node.named_children:
            visit(child, active, breakables, labels, inside_callable)

    visit(tree.root_node)
    return {"loops": loops, "gap": "; ".join(dict.fromkeys(gaps)) if gaps else None}


def ready(path: Path, evidence) -> tuple[bool, str]:
    parsed = inventory(path)
    if parsed["gap"]:
        return False, parsed["gap"]
    if not isinstance(evidence, list) or len(evidence) != len(parsed["loops"]):
        return False, "every parsed loop requires explicit induction evidence"
    fields = {"loop_id", "invariant", "initialization", "preservation", "normal_exit", "abrupt_exits"}
    for loop, proof in zip(parsed["loops"], evidence):
        if not isinstance(proof, dict) or set(proof) != fields or proof.get("loop_id") != loop["loop_id"]:
            return False, "loop evidence does not match the parsed loop identity"
        if any(not isinstance(proof.get(key), str) or not proof[key].strip() or len(proof[key]) > 8000 for key in fields - {"loop_id", "abrupt_exits"}):
            return False, "loop invariant, initialization, preservation and normal exit must be explicit"
        exits = proof["abrupt_exits"]
        if not isinstance(exits, list) or len(exits) != len(loop["abrupt_exits"]):
            return False, "every parsed abrupt loop exit requires an argument"
        for abrupt, argument in zip(loop["abrupt_exits"], exits):
            if not isinstance(argument, dict) or set(argument) != {"exit_id", "argument"} or argument.get("exit_id") != abrupt["exit_id"] or not isinstance(argument.get("argument"), str) or not argument["argument"].strip() or len(argument["argument"]) > 8000:
                return False, "abrupt exit evidence does not match the parsed exit identity"
    return True, ""
