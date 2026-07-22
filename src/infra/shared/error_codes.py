from enum import IntEnum


class ErrorCodes(IntEnum):
    """统一错误码定义"""

    # 成功
    OK = 0

    # 4xxx: 客户端错误
    BAD_REQUEST = 4000
    VALIDATION_ERROR = 4003
    NOT_FOUND = 4004
    UNAUTHORIZED = 4010
    RATE_LIMITED = 4029

    # 5xxx: 服务端错误
    INTERNAL_ERROR = 5000
    SERVICE_SHUTTING_DOWN = 5003
    DATABASE_ERROR = 5005
    EMBEDDING_ERROR = 5006
    CONFLICT = 5009


__all__ = ["ErrorCodes"]
