from app.events.models import AlertEvent


class EventStore:
    """
    Temporary event repository.

    Keeps alert persistence isolated from alert generation.
    """

    def __init__(self) -> None:
        self._events: list[AlertEvent] = []

    def add(self, event: AlertEvent) -> AlertEvent:
        self._events.append(event)
        return event

    def add_many(
        self,
        events: list[AlertEvent],
    ) -> list[AlertEvent]:

        self._events.extend(events)
        return events

    def get_all(self) -> list[AlertEvent]:
        return list(self._events)

    def get_by_site(
        self,
        site_id: str,
    ) -> list[AlertEvent]:

        return [
            event
            for event in self._events
            if event.site_id == site_id
        ]

    def clear(self) -> None:
        self._events.clear()