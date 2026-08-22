"""Errors raised while converting authored capabilities into domain models."""


class CapabilityBuildError(ValueError):
    """Report structured capability content that cannot be built."""

    def __init__(
        self,
        *,
        content: str,
        location: str,
        mechanic: str,
    ) -> None:
        self.content = content
        self.location = location
        self.mechanic = mechanic
        super().__init__(f"{content}: unsupported {mechanic} at {location}.")
