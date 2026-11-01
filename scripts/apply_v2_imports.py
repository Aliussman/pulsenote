"""Point src/grounding.py at the shared src/textnorm.py module (validator-v2).

Removes the old top-level definitions of the text helpers from grounding.py and adds one
import, so the grounding validator and the post-hoc check use identical normalisation.
Uses the Python parser, so it works even if you have edited those helpers since v1.
A backup is written to src/grounding.py.bak. Run with --dry-run first to see what it would do.

Usage:  python scripts/apply_v2_imports.py [--dry-run] [--path src/grounding.py]
"""

import argparse
import ast
import shutil

REMOVE = {"NUMBER_WORDS", "NEGATION_CUES", "STOPWORDS", "NUM_RE", "normalize", "stem", "content_words", "numbers", "has_negation"}
IMPORT = "from .textnorm import content_words, has_negation, normalize, numbers\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="src/grounding.py")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source = open(args.path).read()
    if IMPORT.strip() in source:
        print("already uses src/textnorm.py, nothing to do")
        return
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    spans, removed = [], []
    for node in tree.body:
        names = []
        if isinstance(node, ast.FunctionDef):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        if names and all(n in REMOVE for n in names):
            start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
            spans.append((start, node.end_lineno))
            removed += names

    last_import = max((n.end_lineno for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))), default=0)
    print("will remove:", ", ".join(removed) or "nothing")
    print(f"will add after line {last_import}: {IMPORT.strip()}")
    print("leftover helpers you wrote yourself (for example compound-number helpers) are untouched; delete them by hand if unused")
    if args.dry_run:
        return

    for start, end in sorted(spans, reverse=True):
        del lines[start - 1 : end]
        if start - 1 < len(lines) and lines[start - 1].strip() == "" and start - 2 >= 0 and lines[start - 2].strip() == "":
            del lines[start - 1]
    insert_at = last_import if last_import <= len(lines) else len(lines)
    lines.insert(insert_at, IMPORT)
    new_source = "".join(lines)
    ast.parse(new_source)  # refuse to write a file that does not parse
    shutil.copy(args.path, args.path + ".bak")
    open(args.path, "w").write(new_source)
    print(f"updated {args.path} (backup at {args.path}.bak)")


if __name__ == "__main__":
    main()
