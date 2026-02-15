"""Tests for the multiplexed output function factory."""

from claude_teletype.output import make_output_fn
from claude_teletype.pacer import pace_characters


def test_single_destination_receives_every_character():
    """A single destination gets every character passed to output_fn."""
    collected: list[str] = []
    output_fn = make_output_fn(collected.append)

    for char in "Hello":
        output_fn(char)

    assert collected == ["H", "e", "l", "l", "o"]


def test_multiple_destinations_each_receive_every_character():
    """Multiple destinations each get every character in order."""
    dest_a: list[str] = []
    dest_b: list[str] = []
    dest_c: list[str] = []
    output_fn = make_output_fn(dest_a.append, dest_b.append, dest_c.append)

    for char in "AB":
        output_fn(char)

    assert dest_a == ["A", "B"]
    assert dest_b == ["A", "B"]
    assert dest_c == ["A", "B"]


def test_zero_destinations_does_not_raise():
    """Calling output_fn with zero destinations is a safe no-op."""
    output_fn = make_output_fn()
    # Should not raise
    output_fn("x")
    output_fn("\n")
    output_fn("")


def test_destination_call_order_is_preserved():
    """Destinations are called in the order they were provided."""
    call_order: list[str] = []
    dest_a = lambda char: call_order.append(f"a:{char}")  # noqa: E731
    dest_b = lambda char: call_order.append(f"b:{char}")  # noqa: E731
    output_fn = make_output_fn(dest_a, dest_b)

    output_fn("X")

    assert call_order == ["a:X", "b:X"]


async def test_integration_with_pacer():
    """output_fn receives individual characters when used with pace_characters."""
    collected: list[str] = []
    output_fn = make_output_fn(collected.append)

    await pace_characters("Hi", base_delay_ms=0, output_fn=output_fn)

    assert collected == ["H", "i"]


async def test_integration_with_pacer_multiple_destinations():
    """Multiple destinations each receive individual characters via pacer."""
    dest_a: list[str] = []
    dest_b: list[str] = []
    output_fn = make_output_fn(dest_a.append, dest_b.append)

    await pace_characters("Ok", base_delay_ms=0, output_fn=output_fn)

    assert dest_a == ["O", "k"]
    assert dest_b == ["O", "k"]
