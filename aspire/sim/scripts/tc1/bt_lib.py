# ===== BT_LIB BEGIN (paste verbatim from scripts/tc1/bt_lib.py; bt_check.py verifies) =====
# Minimal behaviour tree for evosearch_bt candidates. Every Action has a check, written by the
# candidate, that tests the action's effect; a failed check re-runs the action (retries) within the
# step and time budget. Motion only through bt_move / bt_move_pose / bt_open / bt_close, inside an Action.
# Node functions take the blackboard dict `bb` (shared state written and read by the nodes).
# Custom nodes: any class with tick(bb) -> SUCCESS/FAILURE; it may tick children and call bt_fail,
# but never touches _bt* names (bt_check.py rejects that) and moves only through Action children.
import time as _bt_time

import numpy as _bt_np

SUCCESS, FAILURE = "SUCCESS", "FAILURE"
BT_STEP_BUDGET = 4000   # episode limit in sim steps (FrankaLiberoEnv max_steps)
BT_TIME_BUDGET_S = 160  # evosearch_eval kills a trial at 180 s wall clock
BT_MOVE_COST = 120      # max sim steps per move_to_joints call
BT_GRIPPER_COST = 30    # sim steps per open_gripper / close_gripper call
_bt = {"steps": 0, "t0": _bt_time.time(), "action": None, "fails": []}


def bt_steps_left():
    return BT_STEP_BUDGET - _bt["steps"]


def bt_time_left():
    return BT_TIME_BUDGET_S - (_bt_time.time() - _bt["t0"])


def _bt_need_action(fn):
    if _bt["action"] is None:
        raise RuntimeError(f"{fn} called outside an Action")


def bt_move(joints):
    """One move_to_joints call, counted as BT_MOVE_COST steps."""
    _bt_need_action("bt_move")
    _bt["steps"] += BT_MOVE_COST
    move_to_joints(joints)


def bt_move_pose(pos, quat):
    """solve_ik + one bt_move. Returns the target joints, or None if solve_ik returned None."""
    _bt_need_action("bt_move_pose")
    joints = solve_ik(_bt_np.asarray(pos, dtype=float).tolist(), _bt_np.asarray(quat, dtype=float).tolist())
    if joints is None:
        return None
    bt_move(joints)
    return _bt_np.asarray(joints, dtype=float)


def bt_open():
    _bt_need_action("bt_open")
    _bt["steps"] += BT_GRIPPER_COST
    open_gripper()


def bt_close():
    _bt_need_action("bt_close")
    _bt["steps"] += BT_GRIPPER_COST
    close_gripper()


# ---- nodes ----
class Action:
    """Run act(bb), then check(bb). Retry act while the check fails, up to `retries` extra tries.
    act returning False means the try failed without checking .
    cost = sim steps one try may use (budget guard); check is REQUIRED."""

    def __init__(self, name, act, check, retries=2, cost=BT_MOVE_COST):
        if check is None:
            raise ValueError(f"Action {name}: check is required")
        self.name, self.act, self.check, self.retries, self.cost = name, act, check, retries, cost

    def tick(self, bb):
        for k in range(self.retries + 1):
            if bt_steps_left() < self.cost or bt_time_left() <= 0:
                return _bt_fail(self.name, k, "budget")
            _bt["action"] = self.name
            try:
                ok = self.act(bb) is not False
            finally:
                _bt["action"] = None
            if ok and self.check(bb):
                if k:
                    print(f"[BT] {self.name}: ok after {k + 1} tries", flush=True)
                return SUCCESS
        return _bt_fail(self.name, self.retries + 1, "check")


class Condition:
    def __init__(self, name, check):
        self.name, self.check = name, check

    def tick(self, bb):
        return SUCCESS if self.check(bb) else _bt_fail(self.name, 1, "cond")


class Sequence:
    """SUCCESS if all children succeed in order; stops at the first FAILURE."""

    def __init__(self, name, children):
        self.name, self.children = name, children

    def tick(self, bb):
        for c in self.children:
            if c.tick(bb) == FAILURE:
                return FAILURE
        return SUCCESS


class Fallback:
    """Try children in order; SUCCESS at the first child that succeeds."""

    def __init__(self, name, children):
        self.name, self.children = name, children

    def tick(self, bb):
        for c in self.children:
            if c.tick(bb) == SUCCESS:
                return SUCCESS
        return _bt_fail(self.name, len(self.children), "all children failed")


class Retry:
    """Re-tick a whole subtree up to `times` times."""

    def __init__(self, name, child, times=2):
        self.name, self.child, self.times = name, child, times

    def tick(self, bb):
        for k in range(self.times):
            if self.child.tick(bb) == SUCCESS:
                return SUCCESS
            if bt_steps_left() < BT_MOVE_COST or bt_time_left() <= 0:
                break
        return _bt_fail(self.name, self.times, "retries exhausted")


class Do:
    """Non-motion step (perception, planning, writing bb). fn(bb) returning False = FAILURE."""

    def __init__(self, name, fn):
        self.name, self.fn = name, fn

    def tick(self, bb):
        return SUCCESS if self.fn(bb) is not False else _bt_fail(self.name, 1, "returned False")


def _bt_fail(name, tries, why):
    _bt["fails"].append(name)
    print(f"[BT] {name}: FAIL ({why}, tries={tries})", flush=True)
    return FAILURE


def bt_fail(name, tries, why):
    """For custom nodes: report a FAILURE in the same [BT] format and return FAILURE."""
    return _bt_fail(name, tries, why)


def run_tree(root, bb=None):
    """The only entry point. No motion is allowed after it returns."""
    bb = {} if bb is None else bb
    status = root.tick(bb)
    print(f"[BT] RESULT {status} steps~{_bt['steps']} t={_bt_time.time() - _bt['t0']:.0f}s "
          f"fails={','.join(_bt['fails']) or '-'}", flush=True)
    return status
# ===== BT_LIB END =====
