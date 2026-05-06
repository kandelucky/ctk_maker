"""Unit tests for app.core.history.History.

Covers push/undo/redo cycle, suspension during replay, merge-into
coalesce, redo-stack invalidation on push, max-depth cap, and the
``history_changed`` event fanout.
"""
from __future__ import annotations

from app.core.event_bus import EventBus
from app.core.history import MAX_DEPTH, History


class _FakeProject:
    def __init__(self):
        self.event_bus = EventBus()


class _FakeCommand:
    """Minimal Command protocol — undo/redo just append to a log so
    tests can verify the right command runs at the right time.
    Override ``mergeable`` per-instance to control merge_into.
    """

    def __init__(self, label: str, mergeable: bool = False, log=None):
        self.label = label
        self.mergeable = mergeable
        self._log = log if log is not None else []

    def undo(self, project) -> None:
        self._log.append(("undo", self.label))

    def redo(self, project) -> None:
        self._log.append(("redo", self.label))

    def merge_into(self, prev) -> bool:
        # Merge if both commands flagged mergeable AND share label.
        if self.mergeable and getattr(prev, "mergeable", False):
            if prev.label == self.label:
                prev.merged_count = getattr(prev, "merged_count", 1) + 1
                return True
        return False


def _make_history():
    project = _FakeProject()
    return project, History(project)


# ----------------------------------------------------------------------
# Initial state
# ----------------------------------------------------------------------
def test_fresh_history_cannot_undo_or_redo():
    _, history = _make_history()
    assert not history.can_undo()
    assert not history.can_redo()
    assert not history.is_suspended()


# ----------------------------------------------------------------------
# Push / undo / redo cycle
# ----------------------------------------------------------------------
def test_push_makes_undo_available():
    project, history = _make_history()
    history.push(_FakeCommand("A"))
    assert history.can_undo()
    assert not history.can_redo()


def test_undo_replays_command_then_makes_redo_available():
    project, history = _make_history()
    log: list = []
    history.push(_FakeCommand("A", log=log))

    history.undo()
    assert log == [("undo", "A")]
    assert not history.can_undo()
    assert history.can_redo()


def test_redo_replays_command_then_makes_undo_available_again():
    project, history = _make_history()
    log: list = []
    history.push(_FakeCommand("A", log=log))
    history.undo()
    log.clear()

    history.redo()
    assert log == [("redo", "A")]
    assert history.can_undo()
    assert not history.can_redo()


def test_undo_with_empty_stack_is_noop():
    project, history = _make_history()
    history.undo()    # should not raise
    history.redo()


# ----------------------------------------------------------------------
# Push invalidates redo
# ----------------------------------------------------------------------
def test_push_clears_redo_stack():
    project, history = _make_history()
    history.push(_FakeCommand("A"))
    history.undo()
    assert history.can_redo()

    history.push(_FakeCommand("B"))
    assert not history.can_redo()


# ----------------------------------------------------------------------
# Suspension during replay
# ----------------------------------------------------------------------
def test_suspended_flag_set_during_undo_and_redo():
    project, history = _make_history()
    seen_during_undo: list[bool] = []
    seen_during_redo: list[bool] = []

    class _Probe(_FakeCommand):
        def undo(self, p):
            seen_during_undo.append(history.is_suspended())

        def redo(self, p):
            seen_during_redo.append(history.is_suspended())

        def merge_into(self, prev):
            return False

    history.push(_Probe("A"))
    history.undo()
    assert seen_during_undo == [True]
    assert not history.is_suspended()    # cleared after undo

    history.redo()
    assert seen_during_redo == [True]
    assert not history.is_suspended()


def test_push_during_suspended_replay_is_dropped():
    """Re-entrant push during undo/redo replay (e.g. the same UI flow
    that produced the command publishes events that try to record a
    new command) must NOT pollute the stack.
    """
    project, history = _make_history()

    class _ReentrantUndo(_FakeCommand):
        def undo(self, p):
            history.push(_FakeCommand("inner"))

        def merge_into(self, prev):
            return False

    history.push(_ReentrantUndo("outer"))
    history.undo()

    # The reentrant push should be dropped — only "outer" exists,
    # now in the redo stack.
    assert not history.can_undo()
    assert history.can_redo()


# ----------------------------------------------------------------------
# Merge-into coalesce
# ----------------------------------------------------------------------
def test_mergeable_command_collapses_into_predecessor():
    project, history = _make_history()
    first = _FakeCommand("nudge", mergeable=True)
    history.push(first)
    history.push(_FakeCommand("nudge", mergeable=True))
    history.push(_FakeCommand("nudge", mergeable=True))

    # Three pushes but they all merged — one undo unwinds everything.
    assert history.can_undo()
    history.undo()
    assert not history.can_undo()
    # merged_count tracks how many merges happened on the tail.
    assert getattr(first, "merged_count", 0) == 3


def test_non_mergeable_commands_grow_stack():
    project, history = _make_history()
    history.push(_FakeCommand("A"))
    history.push(_FakeCommand("B"))
    history.push(_FakeCommand("C"))

    history.undo()
    history.undo()
    history.undo()
    assert not history.can_undo()


def test_merge_clears_redo_stack():
    project, history = _make_history()
    history.push(_FakeCommand("nudge", mergeable=True))
    history.undo()
    assert history.can_redo()

    history.push(_FakeCommand("nudge", mergeable=True))
    # New mergeable push should merge into the (still existing) prior
    # tail — but the prior tail is now in the REDO stack, not undo.
    # So this push goes to undo as a fresh entry, and redo must clear.
    assert not history.can_redo()


# ----------------------------------------------------------------------
# Clear
# ----------------------------------------------------------------------
def test_clear_empties_both_stacks():
    project, history = _make_history()
    history.push(_FakeCommand("A"))
    history.push(_FakeCommand("B"))
    history.undo()    # one in redo, one in undo

    history.clear()
    assert not history.can_undo()
    assert not history.can_redo()


def test_clear_when_already_empty_is_noop():
    project, history = _make_history()
    history.clear()    # should not raise


# ----------------------------------------------------------------------
# Max depth cap
# ----------------------------------------------------------------------
def test_undo_stack_caps_at_MAX_DEPTH():
    project, history = _make_history()
    # Push MAX_DEPTH + 5 — oldest 5 should be evicted.
    for i in range(MAX_DEPTH + 5):
        history.push(_FakeCommand(f"cmd-{i}"))

    # Pop everything via undo — should get back MAX_DEPTH commands.
    log: list[str] = []
    while history.can_undo():
        # Read the tail label by undoing into a probe that records.
        # Cheap proxy — just count.
        history.undo()
        log.append("undone")

    assert len(log) == MAX_DEPTH


# ----------------------------------------------------------------------
# Event bus integration
# ----------------------------------------------------------------------
def test_history_changed_fires_on_push_undo_redo_clear():
    project, history = _make_history()
    fires: list[None] = []
    project.event_bus.subscribe("history_changed", lambda: fires.append(None))

    history.push(_FakeCommand("A"))
    assert len(fires) == 1

    history.undo()
    assert len(fires) == 2

    history.redo()
    assert len(fires) == 3

    history.clear()
    assert len(fires) == 4


def test_history_changed_does_not_fire_on_empty_undo_redo():
    project, history = _make_history()
    fires: list[None] = []
    project.event_bus.subscribe("history_changed", lambda: fires.append(None))

    history.undo()    # empty — no event
    history.redo()    # empty — no event
    assert fires == []
