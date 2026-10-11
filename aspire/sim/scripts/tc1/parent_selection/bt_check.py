"""Checks and failure tallies for the evosearch_bt arm (behaviour-tree candidates).

  verify  --iter-dir DIR | FILE...   every candidate is a valid BT candidate (prints OK / errors)
  report  --iter-dir DIR | --logs DIR  which BT nodes failed, per candidate (dev) or over seeds (Stage 2)

A valid candidate:
  - contains the block from scripts/tc1/parent_selection/bt_lib.py verbatim (BT_LIB BEGIN .. END)
  - never calls move_to_joints / open_gripper / close_gripper / goto_home_joint_position itself
    (motion only via bt_move / bt_move_pose / bt_open / bt_close, which raise outside an Action)
  - gives every Action(...) a check that is not None and not a constant (lambda bb: True)
  - calls run_tree(...) and no bt_* motion at module level
  - never references BT_LIB internals (_bt*); custom node classes are allowed
  - uses none of the forbidden simulator APIs
iter_00/candidate_A is START_CODE verbatim and is skipped.
"""
import argparse
import ast
import re
import sys
from collections import Counter
from pathlib import Path

BEGIN = "# ===== BT_LIB BEGIN"
END = "# ===== BT_LIB END ====="
LIB = Path(__file__).with_name("bt_lib.py")
RAW_MOTION = {"move_to_joints", "open_gripper", "close_gripper", "goto_home_joint_position"}
BT_MOTION = {"bt_move", "bt_move_pose", "bt_open", "bt_close"}
FORBIDDEN = [r"\.sim\.data", r"\.sim\.model", r"sim\.forward\(", r"env\.handle\.env\b", r"parsed_problem",
             r"_eval_predicate", r"obj_body_id", r"_step_once\(", r"\.bddl\b", r"\.urdf\b"]


def lib_block():
    text = LIB.read_text()
    return text[text.index(BEGIN):text.index(END) + len(END)]


def call_name(node):
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def is_constant_check(node):
    if isinstance(node, ast.Constant):
        return True
    return isinstance(node, ast.Lambda) and isinstance(node.body, ast.Constant)


def verify_file(path):
    errs = []
    code = path.read_text()
    block = lib_block()
    if block not in code:
        errs.append("BT_LIB block missing or edited (paste scripts/tc1/parent_selection/bt_lib.py verbatim)")
        rest = code
    else:
        rest = code.replace(block, "")
    for pat in FORBIDDEN:
        if re.search(pat, rest):
            errs.append(f"forbidden API pattern {pat!r}")
    try:
        tree = ast.parse(rest)
    except SyntaxError as e:
        return errs + [f"syntax error: {e}"]
    run_tree_calls = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id.startswith("_bt"):
            errs.append(f"line {node.lineno}: {node.id} is BT_LIB internal state (custom nodes use bt_fail / Action)")
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node)
        if name in RAW_MOTION:
            errs.append(f"line {node.lineno}: raw {name}() -- use bt_* inside an Action")
        elif name == "run_tree":
            run_tree_calls += 1
        elif name == "Action":
            check = node.args[2] if len(node.args) >= 3 else next(
                (k.value for k in node.keywords if k.arg == "check"), None)
            if check is None or is_constant_check(check):
                errs.append(f"line {node.lineno}: Action without a real check")
    if run_tree_calls == 0:
        errs.append("run_tree(...) never called")
    for node in module_level_nodes(tree):  # no motion outside the tree
        if isinstance(node, ast.Call) and call_name(node) in BT_MOTION:
            errs.append(f"line {node.lineno}: {call_name(node)}() at module level")
    return errs


def module_level_nodes(tree):
    """Nodes executed at import time: skips function, lambda and class bodies."""
    todo = list(tree.body)
    while todo:
        node = todo.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        yield node
        todo.extend(ast.iter_child_nodes(node))


def candidate_files(iter_dir):
    files = sorted(Path(iter_dir).glob("candidate_*/code.py"))
    if Path(iter_dir).name == "iter_00":
        files = [f for f in files if f.parent.name != "candidate_A"]
    return files


def cmd_verify(args):
    files = candidate_files(args.iter_dir) if args.iter_dir else [Path(f) for f in args.files]
    if not files:
        print("no candidate files found")
        return 1
    bad = 0
    for f in files:
        errs = verify_file(f)
        label = f.parent.name if f.name == "code.py" else str(f)
        print(f"{label}: {'OK' if not errs else 'FAIL'}")
        for e in errs:
            print(f"  - {e}")
        bad += bool(errs)
    print("OK" if not bad else f"{bad} candidate(s) FAIL")
    return 1 if bad else 0


FAIL_RE = re.compile(r"\[BT\] (.+?): FAIL \(([^,]+)")


def tally(texts):
    fails, results = Counter(), Counter()
    for t in texts:
        for node, why in set(FAIL_RE.findall(t)):  # once per trial
            fails[f"{node} ({why})"] += 1
        m = re.search(r"\[BT\] RESULT (\w+)", t)
        results[m.group(1) if m else "no RESULT line (crash/timeout?)"] += 1
    return fails, results


def show(label, texts):
    fails, results = tally(texts)
    print(f"{label}: {len(texts)} trials, tree " + ", ".join(f"{k} {v}" for k, v in results.most_common()))
    for k, v in fails.most_common(8):
        print(f"    {v:3d}x  {k}")


def cmd_report(args):
    if args.logs:
        show(args.logs, [p.read_text(errors="replace") for p in sorted(Path(args.logs).glob("seed_*.log"))])
        return 0
    for cand in sorted(Path(args.iter_dir).glob("candidate_*")):
        texts = [p.read_text(errors="replace") for p in cand.glob("eval/trial_*/summary.txt")]
        if texts:
            show(cand.name, texts)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--iter-dir")
    v.add_argument("files", nargs="*")
    r = sub.add_parser("report")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--iter-dir")
    g.add_argument("--logs", help="Stage 2 runs/<id>/logs directory")
    args = ap.parse_args()
    sys.exit(cmd_verify(args) if args.cmd == "verify" else cmd_report(args))


if __name__ == "__main__":
    main()
