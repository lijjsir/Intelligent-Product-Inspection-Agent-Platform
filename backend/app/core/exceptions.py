class AppError(Exception):
    code = "app_error"
    status_code = 400


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404


class ForbiddenError(AppError):
    code = "forbidden"
    status_code = 403


class ConflictError(AppError):
    code = "conflict"
    status_code = 409


class ValidationError(AppError):
    code = "validation_error"
    status_code = 422


class ServiceUnavailableError(AppError):
    code = "service_unavailable"
    status_code = 503
