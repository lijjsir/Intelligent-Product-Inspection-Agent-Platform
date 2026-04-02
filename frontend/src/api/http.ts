import axios, { type AxiosInstance, type AxiosRequestConfig } from "axios";
import { clearStoredAuthSession, ORG_ID_KEY, TOKEN_KEY, readStoredValue } from "@/utils/auth-session";

const apiBase = import.meta.env.VITE_API_BASE ?? "/api";
let handlingAuthFailure = false;

export interface ApiEnvelope<T> {
  code: string | number;
  message: string;
  data: T;
  meta?: {
    page?: number;
    page_size?: number;
    total?: number;
    request_id?: string;
  };
}

const instance: AxiosInstance = axios.create({
  baseURL: apiBase,
  timeout: 15000,
});

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

instance.interceptors.response.use(
  (response: any) => response,
  (error: any) => {
    const response = error.response;
    const serverMessage = response?.data?.message;
    const requestUrl = String(error?.config?.url || "");
    const isLoginTokenRequest = requestUrl.includes("/v1/auth/token");
    if (response) {
      if (response.status === 401) {
        if (isLoginTokenRequest) {
          showToast(serverMessage || "登录失败，请检查组织 ID、账号和密码");
          return Promise.reject(error);
        }
        clearStoredAuthSession();
        if (!handlingAuthFailure) {
          handlingAuthFailure = true;
          showToast(serverMessage || "登录已失效，请重新登录");
          redirectToLogin();
        }
      } else if (response.status === 403) {
        showToast(serverMessage || "当前请求被后端拒绝，请检查组织 ID、账号和权限");
      } else {
        showToast(serverMessage || "请求失败");
      }
    } else {
      if (isLoginTokenRequest) {
        showToast("后端连接失败，登录接口不可达，请确认后端服务和端口已启动");
      } else {
        showToast("后端连接失败，请确认后端服务和端口已启动");
      }
    }
    return Promise.reject(error);
  },
);

export const http = {
  get: <T>(url: string, config?: AxiosRequestConfig) => instance.get<ApiEnvelope<T>>(url, config),
  post: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) => instance.post<ApiEnvelope<T>>(url, data, config),
  put: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) => instance.put<ApiEnvelope<T>>(url, data, config),
  patch: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) => instance.patch<ApiEnvelope<T>>(url, data, config),
  delete: <T>(url: string, config?: AxiosRequestConfig) => instance.delete<ApiEnvelope<T>>(url, config),
};

export default instance;
