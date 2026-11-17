from __future__ import annotations

import pytest

from tool_update_49.download import plan_segments


@pytest.mark.parametrize("total", [2 << 20, 3_000_000, 5 << 20, 100 << 20])
def test_plan_segments_covers_whole_file(total: int) -> None:
    segments = plan_segments(total)
    assert 1 <= len(segments) <= 5
    assert segments[0].start == 0
    assert segments[-1].end == total - 1
    for left, right in zip(segments[:-1], segments[1:], strict=True):
        assert left.end + 1 == right.start
    assert sum(segment.end - segment.start + 1 for segment in segments) == total


def test_plan_segments_single() -> None:
    segments = plan_segments(1 << 20)
    assert len(segments) == 1
    assert segments[0].start == 0
    assert segments[0].end == (1 << 20) - 1


def test_plan_segments_rejects_empty() -> None:
    with pytest.raises(ValueError):
        plan_segments(0)
