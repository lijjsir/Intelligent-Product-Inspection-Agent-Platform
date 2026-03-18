from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    super_admin = "super_admin"
    org_admin = "org_admin"
    inspector = "inspector"
    analyst = "analyst"
    api_service = "api_service"
    auditor = "auditor"


@dataclass(frozen=True)
class User:
    id: str
    org_id: str
    username: str
    email: str
    role: Role
