import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { authApi } from "@/api/auth.api";
import type { LoginPayload, RegisterPayload, AuthSession } from "@/types/auth.types";

const TOKEN_KEY = "piap_token";
const ORG_ID_KEY = "piap_org_id";
const ROLE_KEY = "piap_role";
const USER_ID_KEY = "piap_user_id";

export const useAuthStore = defineStore("auth", () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || "");
  const orgId = ref(localStorage.getItem(ORG_ID_KEY) || "");
  const role = ref(localStorage.getItem(ROLE_KEY) || "");
  const userId = ref(localStorage.getItem(USER_ID_KEY) || "");

  const isAuthed = computed(() => Boolean(token.value));

  function setSession(session: AuthSession) {
    console.log("设置会话数据:", session);
    token.value = session.access_token;
    orgId.value = session.org_id;
    role.value = session.role;
    userId.value = session.user_id;

    localStorage.setItem(TOKEN_KEY, token.value);
    localStorage.setItem(ORG_ID_KEY, orgId.value);
    localStorage.setItem(ROLE_KEY, role.value);
    localStorage.setItem(USER_ID_KEY, userId.value);
    console.log("会话设置完成，isAuthed:", isAuthed.value);
  }

  async function login(payload: LoginPayload) {
    const { data } = await authApi.login(payload);
    console.log("登录 API 响应:", data);
    console.log("解析的会话数据:", data.data);
    setSession(data.data);
    return data.data;
  }

  async function register(payload: RegisterPayload) {
    const { data } = await authApi.register(payload);
    setSession(data.data);
    return data.data;
  }

  function logout() {
    token.value = "";
    orgId.value = "";
    role.value = "";
    userId.value = "";
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ORG_ID_KEY);
    localStorage.removeItem(ROLE_KEY);
    localStorage.removeItem(USER_ID_KEY);
  }

  return { token, orgId, role, userId, isAuthed, login, register, logout };
});
