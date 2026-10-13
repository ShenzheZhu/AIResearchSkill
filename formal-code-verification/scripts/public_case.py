#!/usr/bin/env python3
"""Prepare and replay one authentic, dependency-free public verification case."""

import argparse
import ast
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import shutil


REPOSITORY = "https://github.com/more-itertools/more-itertools.git"
REVISIONS = {
    "historical": "1da45ae4b61a832ed080f08a8833784aad0a9534",
    "fixed": "b5e3886a37209bb880f17d82fbf4ba00ece0e41e",
}
PROBE = r'''
import json
from more_itertools import seekable

cases = [
    ("zero_peek", [10, 20, 30], 0, "peek"),
    ("zero_bool", [10, 20, 30], 0, "bool"),
    ("zero_repeated_peek", [10, 20, 30], 0, "repeat"),
    ("zero_falsy_peek", [None, False, 0], 0, "peek"),
    ("zero_empty_bool", [], 0, "bool"),
    ("zero_empty_peek", [], 0, "peek"),
    ("default_peek", [10, 20, 30], None, "peek"),
    ("bounded_peek", [10, 20, 30], 1, "peek"),
]
rows = []
for name, values, maxlen, action in cases:
    instance = seekable(values, maxlen=maxlen)
    if action == "bool":
        expected = bool(values)
    elif not values:
        expected = "StopIteration"
    else:
        expected = [values[0], values[0]] if action == "repeat" else values[0]
    try:
        actual = bool(instance) if action == "bool" else (
            [instance.peek(), instance.peek()] if action == "repeat" else instance.peek()
        )
    except StopIteration:
        actual = "StopIteration"
    remaining = list(instance)
    cache = list(instance.elements())
    passed = actual == expected and remaining == values
    passed = passed and (maxlen is None or len(cache) <= maxlen)
    rows.append(dict(case=name, expected=expected, actual=actual,
                     expected_remaining=values, remaining=remaining,
                     cache=cache, passed=passed))
print(json.dumps(rows, sort_keys=True))
'''


def git(*arguments, cwd=None):
    return subprocess.check_output(["git", *arguments], cwd=cwd)


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    upstream = output / "upstream"
    git("clone", "--quiet", "--filter=blob:none", "--no-checkout", REPOSITORY, str(upstream))
    revisions = {**REVISIONS, "latest": git("rev-parse", "origin/HEAD", cwd=upstream).decode().strip()}
    for label, revision in revisions.items():
        destination = output / "native" / label
        archive = git("archive", revision, "more_itertools", "LICENSE", cwd=upstream)
        with tarfile.open(fileobj=io.BytesIO(archive)) as files:
            for member in files:
                if member.isfile():
                    path = destination / member.name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(files.extractfile(member).read())
    source = (output / "native/historical/more_itertools/more.py").read_text()
    classes = [node for node in ast.parse(source).body
               if isinstance(node, ast.ClassDef) and node.name in {"SequenceView", "seekable"}]
    start, end = classes[0].lineno, classes[-1].end_lineno
    analysis = output / "analysis"
    selected = analysis / "selected"
    selected.mkdir(parents=True)
    excerpt = "".join(source.splitlines(keepends=True)[start - 1:end])
    (selected / "more.py").write_text(excerpt)
    shutil.copytree(output / "native/historical/more_itertools", analysis / "native/more_itertools")
    (analysis / "LICENSE").write_bytes((output / "native/historical/LICENSE").read_bytes())
    (analysis / "README.md").write_text(
        "# Selected public API analysis\n\n"
        f"`selected/more.py` is an unchanged excerpt of `{REPOSITORY}` at "
        f"`{revisions['historical']}`, `more_itertools/more.py` lines {start}–{end}. "
        f"Selected line 1 maps to original line {start}. Read its public docstrings as requirements.\n\n"
        "This excerpt is an analysis artifact, not an independently executable package. "
        "The entire unchanged package is at `native/more_itertools` within this repository. "
        "For actual public entry probes, use an installed Python 3.10 or newer, "
        "set `PYTHONPATH` to `native` (resolved from this directory), "
        "and import `seekable` from `more_itertools`. No installation is required. "
        "Do not edit native package files.\n"
    )
    git("init", "--quiet", cwd=analysis)
    git("add", "README.md", "LICENSE", "selected/more.py", "native", cwd=analysis)
    git("-c", "user.name=Public case fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "--quiet", "-m", "Prepare selected public API", cwd=analysis)
    metadata = dict(repository=REPOSITORY, revisions=revisions,
                    source_file="more_itertools/more.py", original_lines=[start, end],
                    analysis_directory="analysis", native_directory="native",
                    python=sys.version.split()[0])
    (output / "case.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


def replay(output):
    (output / "replay.json").unlink(missing_ok=True)
    metadata = json.loads((output / "case.json").read_text())
    results = {}
    for label, revision in metadata["revisions"].items():
        command = [sys.executable, "-B", "-c", PROBE]
        directory = output / "native" / label
        process = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=15)
        (output / f"replay-{label}.log").write_text(process.stdout + process.stderr)
        if process.returncode:
            raise RuntimeError(f"{label} probe infrastructure failed: {process.stderr}")
        rows = json.loads(process.stdout)
        results[label] = dict(revision=revision, command=command, cwd=str(directory),
                              exit_code=process.returncode, cases=rows,
                              passed=sum(row["passed"] for row in rows), total=len(rows))
    failed = {row["case"] for row in results["historical"]["cases"] if not row["passed"]}
    matched = failed == {"zero_peek", "zero_bool", "zero_repeated_peek", "zero_falsy_peek"}
    matched = matched and all(results[label]["passed"] == results[label]["total"]
                              for label in ("fixed", "latest"))
    report = dict(kind="historical-replay-not-new-defect", matched=matched, results=results)
    (output / "replay.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(kind=report["kind"], matched=matched,
                         results={key: {name: row[name] for name in ("revision", "passed", "total")}
                                  for key, row in results.items()}), indent=2))
    return 0 if matched else 1


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        raise SystemExit("Use an installed Python 3.10 or newer; do not install dependencies.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "replay"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sys.exit(prepare(args.output.resolve()) if args.command == "prepare" else replay(args.output.resolve()))
