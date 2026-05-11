from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    admin = "admin"
    app_developer = "app_developer"
    platform_operator = "platform_operator"
    algorithm_engineer = "algorithm_engineer"
    user = "user"
    expert = "expert"
    api_service = "api_service"


@dataclass(frozen=True)
class User:
    id: str
    org_id: str
    username: str
    email: str
    role: Role
