"""Public model failure details without request bodies, credentials or URLs."""
from __future__ import annotations

import httpx


def model_failure(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        try:
            error = response.json().get("error") or {}
            code = str(error.get("code") or "") if isinstance(error, dict) else ""
        except (ValueError, AttributeError):
            code = ""
        if code == "InvalidEndpoint.ClosedEndpoint":
            return "模型服务端点已关闭或暂不可用，请启用该端点或切换模型。", True
        if response.status_code in {401, 403}:
            return "模型服务鉴权失败或没有调用权限，请检查密钥与模型授权。", True
        if response.status_code in {404, 408, 429} or response.status_code >= 500:
            return f"模型服务暂不可用（HTTP {response.status_code}），可调整配置后重新检测。", True
        return f"模型服务拒绝了请求（HTTP {response.status_code}），请核对接口与图片格式。", False
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return "无法连接模型服务或调用超时，请检查网络与模型服务后重新检测。", True
    return "模型返回内容无法解析，请核对模型能力后重新检测。", False
