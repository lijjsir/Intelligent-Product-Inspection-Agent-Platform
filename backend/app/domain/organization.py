from dataclasses import dataclass


@dataclass(frozen=True)
class Organization:
    id: str
    name: str
    slug: str
