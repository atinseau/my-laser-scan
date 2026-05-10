"""Tests unitaires sur road2track_core.queues."""

from __future__ import annotations

from road2track_core.queues import TaskQueue


def test_task_queue_values() -> None:
    """Les valeurs des queues doivent être stables (utilisées par les workers)."""
    assert TaskQueue.CPU.value == "cpu"
    assert TaskQueue.GPU.value == "gpu"
    assert TaskQueue.WINDOWS_TOOLS.value == "windows-tools"


def test_task_queue_is_str_enum() -> None:
    """StrEnum permet d'utiliser la queue directement comme string."""
    assert TaskQueue.CPU == "cpu"
    assert f"queue: {TaskQueue.CPU}" == "queue: cpu"
