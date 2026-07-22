from .error_codes import ErrorCodes


class ApiResponse:
    """统一 API 响应构造器"""

    @classmethod
    def success(cls, data=None, message: str = "success"):
        resp = {"code": ErrorCodes.OK, "status": "success", "message": message}
        if data is not None:
            resp["data"] = data
        return resp

    @classmethod
    def error(cls, error_code: int, message: str, data=None):
        resp = {"code": error_code, "status": "error", "message": message}
        if data is not None:
            resp["data"] = data
        return resp


# 向后兼容别名
class Response(ApiResponse):
    @classmethod
    def success_response(cls, data):
        return cls.success(data=data)

    @classmethod
    def error_response(cls, error_code, error_message):
        return cls.error(error_code, error_message)
