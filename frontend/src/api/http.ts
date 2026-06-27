import axios, { type AxiosInstance, type AxiosRequestConfig } from "axios";
import { clearStoredAuthSession, ORG_ID_KEY, TOKEN_KEY, readStoredValue } from "@/utils/auth-session";

const apiBase = String(import.meta.env.VITE_API_BASE ?? "/api").trim();
let handlingAuthFailure = false;

export interface ApiEnvelope<T> {
  success?: boolean;
  code: string | number;
  message: string;
  data: T;
  trace_id?: string;
  warnings?: Array<string | Record<string, unknown>>;
  meta?: {
    page?: number;
    page_size?: number;
    total?: number;
    request_id?: string;
  };
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  detail?: unknown;
  module?: string;
  trace_id?: string;
  suggestion?: string;
}

export interface ApiRequestConfig extends AxiosRequestConfig {
  suppressErrorToast?: boolean;
}

const instance: AxiosInstance = axios.create({
  baseURL: apiBase,
  timeout: 60000,
});

function isTimeoutError(error: unknown): boolean {
  return axios.isAxiosError(error) && (error.code === "ECONNABORTED" || /timeout/i.test(String(error.message || "")));
}

export function extractApiErrorMessage(error: unknown, fallback = "请求失败"): string {
  return extractApiErrorDetail(error, fallback).message;
}

export function extractApiErrorDetail(error: unknown, fallback = "请求失败"): ApiErrorDetail {
  const maybeResponseData =
    error && typeof error === "object"
      ? (error as { response?: { data?: unknown } }).response?.data
      : undefined;
  if (!axios.isAxiosError(error) && maybeResponseData === undefined) {
    return { code: "UNKNOWN_ERROR", message: fallback };
  }
  const data = (axios.isAxiosError(error) ? error.response?.data : maybeResponseData) as any;
  const envelopeError = data?.error;
  if (typeof data?.error_code === "string" && data.error_code.trim()) {
    return {
      code: data.error_code,
      message: String(data?.message || fallback),
      detail: data?.detail,
      module: data?.module,
      trace_id: data?.trace_id,
      suggestion: data?.suggestion,
    };
  }
  if (envelopeError && typeof envelopeError === "object") {
    return {
      code: String(envelopeError.code || data?.code || "UNKNOWN_ERROR"),
      message: String(envelopeError.message || data?.message || fallback),
      detail: envelopeError.detail,
      module: envelopeError.module,
      trace_id: envelopeError.trace_id || data?.trace_id,
      suggestion: envelopeError.suggestion,
    };
  }
  const detail = data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return { code: "UNKNOWN_ERROR", message: detail };
  }
  if (detail && typeof detail === "object") {
    return {
      code: String(detail.code || detail.error_code || data?.code || "UNKNOWN_ERROR"),
      message: String(detail.message || fallback),
      detail: detail.detail,
      module: detail.module,
      trace_id: detail.trace_id || data?.trace_id,
      suggestion: detail.suggestion,
    };
  }
  if (typeof data?.message === "string" && data.message.trim()) {
    return {
      code: String(data?.code || "UNKNOWN_ERROR"),
      message: data.message,
      trace_id: data?.trace_id,
    };
  }
  const errorLike = error as { code?: string; message?: unknown };
  if (typeof errorLike.message === "string" && errorLike.message.trim()) {
    return { code: String(errorLike.code || "UNKNOWN_ERROR"), message: errorLike.message };
  }
  return { code: "UNKNOWN_ERROR", message: fallback };
}

instance.interceptors.request.use((config: any) => {
  const token = readStoredValue(TOKEN_KEY);
  const orgId = readStoredValue(ORG_ID_KEY);
  if (token) {
    config.headers = {
      ...config.headers,
      Authorization: `Bearer ${token}`,
    };
  }
  if (orgId && !(config.headers && ("X-Org-Id" in config.headers))) {
    config.headers = {
      ...config.headers,
      "X-Org-Id": orgId,
    };
  }
  return config;
});

const showToast = (message: string) => {
  const element = document.createElement("div");
  element.textContent = message;
  Object.assign(element.style, {
    position: "fixed",
    top: "20px",
    left: "50%",
    transform: "translateX(-50%)",
    background: "#ef4444",
    color: "white",
    padding: "10px 20px",
    borderRadius: "8px",
    zIndex: "9999",
    boxShadow: "0 4px 6px rgba(0,0,0,0.1)",
    transition: "opacity 0.3s",
    fontSize: "14px",
  });
  document.body.appendChild(element);
  setTimeout(() => {
    element.style.opacity = "0";
    setTimeout(() => element.remove(), 300);
  }, 3000);
};

const redirectToLogin = () => {
  const currentPath = window.location.pathname;
  if (currentPath === "/login" || currentPath === "/register") {
    handlingAuthFailure = false;
    return;
  }
  window.setTimeout(() => {
    window.location.replace("/login");
  }, 0);
};

function isInvalidAuthClaim(responseStatus: number | undefined, detail: ApiErrorDetail): boolean {
  return responseStatus === 403 && detail.code === "forbidden" && detail.message === "invalid token claims";
}

instance.interceptors.response.use(
  (response: any) => response,
  (error: any) => {
    const response = error.response;
    const serverDetail = extractApiErrorDetail(error);
    const serverMessage = serverDetail.message;
    const requestUrl = String(error?.config?.url || "");
    const isLoginTokenRequest = requestUrl.includes("/v1/auth/token");
    const suppressToast = Boolean((error?.config as ApiRequestConfig | undefined)?.suppressErrorToast);
    if (response) {
      if (response.status === 401 || isInvalidAuthClaim(response.status, serverDetail)) {
        if (isLoginTokenRequest) {
          showToast(serverMessage || "登录失败，请检查组织 ID、账号和密码");
          return Promise.reject(error);
        }
        clearStoredAuthSession();
        if (!handlingAuthFailure) {
          handlingAuthFailure = true;
          if (!suppressToast) showToast(serverMessage || "登录已失效，请重新登录");
          redirectToLogin();
        }
      } else if (response.status === 403) {
        if (!suppressToast) showToast(serverMessage || "当前请求被后端拒绝，请检查组织 ID、账号和权限");
      } else {
        if (!suppressToast) showToast(serverMessage || "请求失败");
      }
    } else {
      if (isTimeoutError(error)) {
        if (!suppressToast) showToast("请求超时，后端处理时间过长，请稍后重试");
      } else if (isLoginTokenRequest) {
        showToast("后端连接失败，登录接口不可达，请确认后端服务和端口已启动");
      } else {
        if (!suppressToast) showToast("后端连接失败，请确认后端服务和端口已启动");
      }
    }
    return Promise.reject(error);
  },
);

export const http = {
  get: <T>(url: string, config?: ApiRequestConfig) => instance.get<ApiEnvelope<T>>(url, config),
  post: <T>(url: string, data?: unknown, config?: ApiRequestConfig) => instance.post<ApiEnvelope<T>>(url, data, config),
  put: <T>(url: string, data?: unknown, config?: ApiRequestConfig) => instance.put<ApiEnvelope<T>>(url, data, config),
  patch: <T>(url: string, data?: unknown, config?: ApiRequestConfig) => instance.patch<ApiEnvelope<T>>(url, data, config),
  delete: <T>(url: string, config?: ApiRequestConfig) => instance.delete<ApiEnvelope<T>>(url, config),
};

export default instance;
