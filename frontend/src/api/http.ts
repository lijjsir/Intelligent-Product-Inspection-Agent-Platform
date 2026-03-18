import axios, { type AxiosInstance, type AxiosRequestConfig } from "axios";

const apiBase = import.meta.env.VITE_API_BASE ?? "/api";

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
  const token = localStorage.getItem("piap_token");
  const orgId = localStorage.getItem("piap_org_id");
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

const showToast = (msg: string) => {
  const el = document.createElement("div");
  el.textContent = msg;
  Object.assign(el.style, {
    position: "fixed", top: "20px", left: "50%", transform: "translateX(-50%)",
    background: "#ef4444", color: "white", padding: "10px 20px",
    borderRadius: "8px", zIndex: "9999", boxShadow: "0 4px 6px rgba(0,0,0,0.1)",
    transition: "opacity 0.3s", fontSize: "14px"
  });
  document.body.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 300);
  }, 3000);
};

instance.interceptors.response.use(
  (response: any) => response,
  (error: any) => {
    if (error.response) {
      if (error.response.status === 401) {
        localStorage.removeItem("piap_token");
        showToast("登录已过期，请重新登录");
      } else if (error.response.status === 403) {
        showToast("无权执行此操作");
      } else {
        showToast(error.response.data?.message || "请求失败");
      }
    } else {
      showToast("网络连接引发错误，请稍后重试");
    }
    return Promise.reject(error);
  },
);

export const http = {
  get: <T>(url: string, config?: AxiosRequestConfig) =>
    instance.get<ApiEnvelope<T>>(url, config),
  post: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    instance.post<ApiEnvelope<T>>(url, data, config),
  put: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    instance.put<ApiEnvelope<T>>(url, data, config),
  patch: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    instance.patch<ApiEnvelope<T>>(url, data, config),
  delete: <T>(url: string, config?: AxiosRequestConfig) =>
    instance.delete<ApiEnvelope<T>>(url, config),
};

export default instance;
