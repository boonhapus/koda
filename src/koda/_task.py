from collections.abc import Coroutine
from typing import Any
from weakref import WeakSet, ref as WeakRef
import contextvars
import asyncio
import time


class InstrumentedCoroutine[T]:
    """An awaitable that wraps a coroutine and tracks timing metrics."""
    
    __slots__ = ('_coro', 'create_time', 'start_time', 'end_time', 'cpu_time')
    
    def __init__(self, coro: Coroutine[Any, Any, T]):
        self._coro = coro
        self.create_time: float = time.perf_counter()
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.cpu_time: float = 0.0

    def __await__(self):
        return self._run().__await__()

    async def _run(self) -> T:
        self.start_time = time.perf_counter()
        cpu_start = time.process_time()
        
        try:
            return await self._coro
        finally:
            self.cpu_time = time.process_time() - cpu_start
            self.end_time = time.perf_counter()

    @property
    def queue_latency(self) -> float | None:
        """The total CPU cycle time since the Coroutine was STARTED."""
        if self.start_time is None:
            return None
        return self.start_time - self.create_time
    
    @property
    def wall_time(self) -> float | None:
        """The total execution time since the Coroutine was STARTED."""
        if self.start_time is None:
            return None
        end = self.end_time if self.end_time is not None else time.perf_counter()
        return end - self.start_time

    @property
    def total_time(self) -> float | None:
        """The total elapsed time since the Coroutine was REGISTERED."""
        if self.end_time is None:
            return None
        return self.end_time - self.create_time


class InstrumentedTask[T](asyncio.Task[T]):
    """An implementation of Task which tracks its lineage."""
   
    _all_tasks: WeakSet[InstrumentedTask[Any]] = WeakSet()

    def __init__(
        self,
        coro: Coroutine[Any, Any, T],
        *,
        loop: asyncio.AbstractEventLoop | None = None,
        name: str | None = None,
        context: contextvars.Context | None = None,
        eager_start: bool = False
    ):
        self._parent: WeakRef[InstrumentedTask[Any]] | None = None
        self._children: WeakSet[InstrumentedTask[Any]] = WeakSet()
        self._instrumented = InstrumentedCoroutine(coro)
        self._register_task()
        super().__init__(self._instrumented, loop=loop, name=name, context=context, eager_start=eager_start)

    def _register_task(self) -> None:
        current = asyncio.current_task()

        if isinstance(current, InstrumentedTask):
            self._parent = WeakRef(current)
            current._children.add(self)

        InstrumentedTask._all_tasks.add(self)

    @property
    def parent(self) -> InstrumentedTask[Any] | None:
        """Fetch the parent Task, if one exists."""
        return self._parent() if self._parent else None
    
    @property
    def children(self) -> set[InstrumentedTask[Any]]:
        """Fetch any children of this task."""
        return set(self._children)
    
    @classmethod
    def all_tasks(cls) -> set[InstrumentedTask[Any]]:
        """Fetch all tasks created."""
        return set(cls._all_tasks)
