/// <reference types="vite/client" />

declare module "element-plus/dist/locale/zh-cn.mjs" {
  import type { Language } from "element-plus/es/locale";
  const locale: Language;
  export default locale;
}

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>;
  export default component;
}
