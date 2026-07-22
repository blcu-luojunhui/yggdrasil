import logging
import traceback
from quart import Quart, jsonify
from pydantic import ValidationError

from src.infra.shared import ErrorCodes

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware:
    """
    统一异常处理中间件

    捕获所有未处理的异常，返回标准格式的错误响应
    """

    def __init__(self, app: Quart):
        self.app = app
        app.register_error_handler(Exception, self.handle_exception)
        app.register_error_handler(ValidationError, self.handle_validation_error)

    @staticmethod
    async def handle_validation_error(error: ValidationError):
        """处理 Pydantic 验证错误"""
        errors = error.errors()
        return (
            jsonify(
                {
                    "code": ErrorCodes.VALIDATION_ERROR,
                    "message": "Validation error",
                    "errors": [
                        {
                            "field": ".".join(str(loc) for loc in err["loc"]),
                            "message": err["msg"],
                        }
                        for err in errors
                    ],
                }
            ),
            400,
        )

    async def handle_exception(self, error: Exception):
        """处理通用异常"""
        logger.error(
            f"Unhandled exception: {error}",
            exc_info=True,
            extra={"traceback": traceback.format_exc()},
        )

        return (
            jsonify(
                {
                    "code": ErrorCodes.INTERNAL_ERROR,
                    "message": "Internal server error",
                    "detail": str(error) if self.app.config.get("DEBUG", False) else None,
                }
            ),
            500,
        )


__all__ = ["ErrorHandlerMiddleware"]
