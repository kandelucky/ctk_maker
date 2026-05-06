"""Unit tests for app.core.event_bus.EventBus.

Covers subscribe/publish/unsubscribe semantics, dispatch ordering,
unsubscribe-during-publish reentrance, and no-op behavior on
events with no listeners.
"""
from __future__ import annotations

from app.core.event_bus import EventBus


def test_publish_to_no_listeners_is_noop():
    bus = EventBus()
    # Should not raise even though no one has subscribed.
    bus.publish("nobody_cares")


def test_subscribe_publish_calls_callback_with_args():
    bus = EventBus()
    received: list = []

    def listener(*args, **kwargs):
        received.append((args, kwargs))

    bus.subscribe("ping", listener)
    bus.publish("ping", 1, 2, key="value")

    assert received == [((1, 2), {"key": "value"})]


def test_publish_dispatches_in_subscription_order():
    bus = EventBus()
    order: list[str] = []

    bus.subscribe("evt", lambda: order.append("a"))
    bus.subscribe("evt", lambda: order.append("b"))
    bus.subscribe("evt", lambda: order.append("c"))
    bus.publish("evt")

    assert order == ["a", "b", "c"]


def test_unsubscribe_removes_callback():
    bus = EventBus()
    received: list[int] = []

    def listener():
        received.append(1)

    bus.subscribe("evt", listener)
    bus.publish("evt")
    bus.unsubscribe("evt", listener)
    bus.publish("evt")

    assert received == [1]


def test_unsubscribe_unknown_callback_is_noop():
    bus = EventBus()

    def listener():
        pass

    # Never subscribed — unsubscribe should not raise.
    bus.unsubscribe("evt", listener)
    bus.unsubscribe("never_published", listener)


def test_unsubscribe_during_publish_does_not_skip_later_listeners():
    """Critical correctness property — the publish snapshot
    (``list(self._listeners.get(...))``) protects against listeners
    that unsubscribe themselves or others mid-dispatch from skipping
    the next listener in the original list.
    """
    bus = EventBus()
    received: list[str] = []

    def first():
        received.append("first")
        bus.unsubscribe("evt", second)  # remove the next listener mid-publish

    def second():
        received.append("second")

    def third():
        received.append("third")

    bus.subscribe("evt", first)
    bus.subscribe("evt", second)
    bus.subscribe("evt", third)
    bus.publish("evt")

    # second's removal during dispatch should NOT skip third —
    # publish iterates a snapshot taken at the start of dispatch.
    assert received == ["first", "second", "third"]
    # On the next publish, second is gone.
    received.clear()
    bus.publish("evt")
    assert received == ["first", "third"]


def test_self_unsubscribe_during_publish():
    bus = EventBus()
    received: list[int] = []

    def once():
        received.append(1)
        bus.unsubscribe("evt", once)

    bus.subscribe("evt", once)
    bus.publish("evt")
    bus.publish("evt")
    bus.publish("evt")

    assert received == [1]


def test_subscribe_during_publish_doesnt_fire_in_same_dispatch():
    """A new subscriber added during a publish should not receive
    the in-flight event — it joins for the next publish only.
    The snapshot semantics give us this behaviour for free.
    """
    bus = EventBus()
    received: list[str] = []

    def newcomer():
        received.append("newcomer")

    def adder():
        received.append("adder")
        bus.subscribe("evt", newcomer)

    bus.subscribe("evt", adder)
    bus.publish("evt")
    assert received == ["adder"]    # newcomer not in snapshot

    bus.publish("evt")
    assert received == ["adder", "adder", "newcomer"]


def test_separate_events_have_independent_listener_lists():
    bus = EventBus()
    a_count = [0]
    b_count = [0]

    bus.subscribe("a", lambda: a_count.__setitem__(0, a_count[0] + 1))
    bus.subscribe("b", lambda: b_count.__setitem__(0, b_count[0] + 1))

    bus.publish("a")
    bus.publish("a")
    bus.publish("b")

    assert a_count[0] == 2
    assert b_count[0] == 1


def test_same_callback_subscribed_twice_fires_twice():
    bus = EventBus()
    received: list[int] = []

    def listener():
        received.append(1)

    bus.subscribe("evt", listener)
    bus.subscribe("evt", listener)
    bus.publish("evt")

    assert received == [1, 1]
