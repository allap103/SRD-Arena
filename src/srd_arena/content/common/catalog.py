"""Index authored records by stable name and source identity."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator


class SourceCatalog[T]:
    """Source-aware index for named content records."""

    def __init__(
        self,
        records: Iterable[T],
        *,
        name_of: Callable[[T], str],
        source_of: Callable[[T], str | None],
        source_priority: dict[str, int] | None = None,
    ) -> None:
        self._records: dict[tuple[str, str | None], T] = {}
        self._fallback_priorities: dict[str, int] = {}
        self._record_count = 0
        self._source_records: list[T] = []
        self._source_priority = {
            source.casefold(): priority
            for source, priority in (source_priority or {}).items()
        }
        for record in records:
            self._add(record, name_of(record), source_of(record))

    def find(self, name: str, source: str | None = None) -> T:
        """Find a record case-insensitively, optionally selecting its source.

        >>> records = (("Fireball", "2014"), ("Fireball", "2024"))
        >>> catalog = SourceCatalog(records, name_of=lambda item: item[0],
        ...                         source_of=lambda item: item[1],
        ...                         source_priority={"2024": 1})
        >>> catalog.find("fireball")
        ('Fireball', '2024')
        >>> catalog.find("Fireball", "2014")
        ('Fireball', '2014')
        """
        name_key = name.casefold()
        if source is not None:
            exact = self._records.get((name_key, source.casefold()))
            if exact is not None:
                return exact
        else:
            fallback = self._records.get((name_key, None))
            if fallback is not None:
                return fallback
        source_text = f"|{source}" if source else ""
        raise KeyError(f"Content record '{name}{source_text}' not found.")

    def __len__(self) -> int:
        return self._record_count

    def __iter__(self) -> Iterator[T]:
        return iter(self._source_records)

    def _add(self, record: T, name: str, source: str | None) -> None:
        name_key = name.casefold()
        source_key = source.casefold() if source is not None else None
        exact_key = (name_key, source_key)
        if exact_key in self._records:
            source_text = f"|{source}" if source else ""
            raise ValueError(f"Duplicate content record '{name}{source_text}'.")
        self._records[exact_key] = record
        self._source_records.append(record)
        self._record_count += 1

        fallback_key = (name_key, None)
        priority = self._priority(source)
        if source_key is None:
            self._fallback_priorities[name_key] = priority
            return
        if (
            fallback_key not in self._records
            or priority >= self._fallback_priorities[name_key]
        ):
            self._records[fallback_key] = record
            self._fallback_priorities[name_key] = priority

    def _priority(self, source: str | None) -> int:
        return self._source_priority.get((source or "").casefold(), 0)
