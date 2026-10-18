<script setup lang="ts">
import zhCn from "element-plus/dist/locale/zh-cn.mjs";
import RuntimeEnvironmentBanner from "@/components/common/RuntimeEnvironmentBanner.vue";
</script>

<template>
  <el-config-provider :locale="zhCn">
    <div class="application-root">
      <RuntimeEnvironmentBanner />
      <div class="application-view"><RouterView /></div>
    </div>
  </el-config-provider>
</template>

<style>
.application-root {
  height: 100dvh;
  display: flex;
  flex-direction: column;
}
.application-view {
  min-height: 0;
  flex: 1;
  overflow: auto;
}
.application-view > .app-shell,
.application-view > .app-shell > .app-content,
.application-view > .app-shell > .app-sidebar {
  height: 100% !important;
}
.application-view > .auth-layout {
  min-height: calc(100dvh - var(--runtime-banner-height, 0px));
}
:root .el-overlay .el-drawer.rtl,
:root .el-overlay .el-drawer.ltr {
  top: var(--runtime-banner-height, 0px);
  height: calc(100% - var(--runtime-banner-height, 0px));
}
.el-message {
  margin-top: var(--runtime-banner-height, 0px);
}
@media (max-width: 700px) {
  .application-view > .app-shell > .app-sidebar {
    top: calc(64px + var(--runtime-banner-height, 0px));
    height: auto !important;
  }
  .application-view .mobile-nav-backdrop {
    top: calc(64px + var(--runtime-banner-height, 0px));
  }
}
</style>
