<template>
  <div class="auth-layout" :data-theme="theme">
    <div class="auth-visual">
      <div class="auth-visual-grid" aria-hidden="true" />
      <div class="auth-orbit auth-orbit-one" aria-hidden="true" />
      <div class="auth-orbit auth-orbit-two" aria-hidden="true" />
      <div class="auth-brand-row">
        <div class="brand-mark brand-mark-auth" aria-label="PIAP 智能检测平台图标">
          <img src="/piap-icon.svg?v=3" alt="" width="64" height="64" />
        </div>
        <div>
          <div class="auth-brand-name">PIAP</div>
          <div class="auth-brand-caption">智能检测平台</div>
        </div>
      </div>
      <div class="auth-copy">
        <p class="auth-kicker">PIAP</p>
        <h1>智能检测<span>平台</span></h1>
        <div class="auth-accent-line" />
        <p class="auth-description">从任务到稳定性评估的一体化<br />质量检测控制台</p>
      </div>
      <div class="auth-feature-row">
        <div class="auth-feature"><span class="auth-feature-icon auth-feature-icon-blue">▥</span><strong>可视化分析</strong><small>数据洞察</small></div>
        <div class="auth-feature"><span class="auth-feature-icon auth-feature-icon-green">✓</span><strong>质量监控</strong><small>风险识别</small></div>
        <div class="auth-feature"><span class="auth-feature-icon auth-feature-icon-purple">▤</span><strong>知识检索</strong><small>智能问答</small></div>
      </div>
      <div class="auth-footnote"><span />高效 · 智能 · 专业 · 可信</div>
    </div>
    <div class="auth-form-panel">
      <button
        class="auth-theme-toggle"
        type="button"
        :aria-label="theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'"
        :title="theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'"
        :aria-pressed="theme === 'dark'"
        @click="toggleTheme"
      >
        <el-icon :size="20"><Sunny v-if="theme === 'dark'" /><Moon v-else /></el-icon>
      </button>
      <RouterView />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { Moon, Sunny } from "@element-plus/icons-vue";

const themeKey = "piap_auth_theme";
const readTheme = (): "light" | "dark" => {
  try {
    const saved = window.localStorage.getItem(themeKey);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // Theme switching still works when browser storage is unavailable.
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
};
const theme = ref(readTheme());
const toggleTheme = () => {
  theme.value = theme.value === "dark" ? "light" : "dark";
  try {
    window.localStorage.setItem(themeKey, theme.value);
  } catch {
    // Keep the current selection for this page even if it cannot be persisted.
  }
};
</script>

<style scoped>
.brand-mark {
  flex: none;
  overflow: hidden;
  border-radius: 14px;
}

.brand-mark-auth {
  width: 64px;
  height: 64px;
  border: 1px solid rgba(109, 214, 236, 0.38);
  background: rgba(4, 18, 39, 0.72);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.26);
}

.auth-layout {
  --auth-panel: radial-gradient(circle at 75% 18%, rgba(213, 224, 255, 0.54), transparent 22%), linear-gradient(180deg, #f8faff 0%, #eef4fc 100%);
  --auth-card: #ffffff;
  --auth-input: #ffffff;
  --auth-text: #13213a;
  --auth-muted: #64748b;
  --auth-border: #dbe5f2;
  --auth-link: #1769e8;
  --auth-hover: #f0f5ff;
  --auth-toggle: #e5eaf9;
  --auth-action: #172235;
  --auth-action-hover: #263b59;
  --auth-action-text: #ffffff;
  --auth-focus: #2563eb;
  --auth-shadow: 0 18px 48px rgba(46, 85, 138, 0.08);
  --el-bg-color: var(--auth-card);
  --el-fill-color-blank: var(--auth-input);
  --el-fill-color-light: var(--auth-hover);
  --el-text-color-primary: var(--auth-text);
  --el-text-color-regular: var(--auth-text);
  --el-text-color-secondary: var(--auth-muted);
  --el-text-color-placeholder: var(--auth-muted);
  --el-border-color: var(--auth-border);
  --el-border-color-hover: var(--auth-focus);
  --el-color-primary: var(--auth-focus);
  --el-checkbox-input-border: 1px solid var(--auth-border);
  --el-checkbox-bg-color: var(--auth-input);
  --el-checkbox-checked-bg-color: var(--auth-action);
  --el-checkbox-checked-input-border-color: var(--auth-action);
  --piap-line: var(--auth-border);
  --piap-blue: var(--auth-focus);
  color-scheme: light;
  display: grid;
  min-height: 100dvh;
  grid-template-columns: minmax(0, 1fr) minmax(420px, 1fr);
  background: var(--auth-card);
}

.auth-layout[data-theme="dark"] {
  --auth-panel: radial-gradient(circle at 75% 18%, rgba(40, 67, 108, 0.25), transparent 35%), #0c1422;
  --auth-card: #152033;
  --auth-input: #101a2b;
  --auth-text: #e8eef8;
  --auth-muted: #a4b2c8;
  --auth-border: #35465f;
  --auth-link: #8bb8ff;
  --auth-hover: #21324b;
  --auth-toggle: #22334d;
  --auth-action: #3878ec;
  --auth-action-hover: #4b89f6;
  --auth-focus: #8bb8ff;
  --auth-shadow: 0 18px 48px rgba(0, 0, 0, 0.2);
  color-scheme: dark;
}

.auth-visual {
  position: relative;
  display: flex;
  min-height: 100%;
  flex-direction: column;
  overflow: hidden;
  padding: 32px clamp(24px, 3.5vw, 56px);
  color: #fff;
  background: radial-gradient(circle at 75% 16%, rgba(50, 122, 232, 0.4), transparent 36%), linear-gradient(145deg, #071120 0%, #0b1930 58%, #102c59 100%);
}

.auth-visual::after {
  position: absolute;
  right: -15%;
  bottom: -24%;
  width: 75%;
  height: 75%;
  border: 1px solid rgba(94, 218, 235, 0.18);
  border-radius: 50%;
  box-shadow: 0 0 0 26px rgba(94, 218, 235, 0.05), 0 0 0 52px rgba(94, 218, 235, 0.035), 0 0 100px rgba(41, 127, 232, 0.32);
  content: "";
}

.auth-orbit {
  position: absolute;
  z-index: 0;
  border: 1px solid rgba(71, 178, 244, 0.25);
  border-radius: 50%;
  transform: rotate(-16deg);
  pointer-events: none;
}
.auth-orbit-one { right: -4%; bottom: 17%; width: 610px; height: 280px; box-shadow: 0 0 0 22px rgba(69, 165, 242, 0.08), 0 0 70px rgba(44, 129, 238, 0.34); }
.auth-orbit-two { right: 5%; bottom: 10%; width: 570px; height: 220px; border-color: rgba(83, 221, 233, 0.2); }

.auth-visual-grid {
  position: absolute;
  inset: 0;
  opacity: 0.22;
  background-image: linear-gradient(rgba(143, 193, 255, 0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(143, 193, 255, 0.08) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: linear-gradient(to bottom, black, transparent 82%);
}

.auth-brand-row,
.auth-copy,
.auth-feature-row,
.auth-footnote { position: relative; z-index: 1; }
.auth-brand-row { display: flex; align-items: center; gap: 16px; }
.auth-brand-name { font-size: 24px; font-weight: 760; letter-spacing: 0.08em; }
.auth-brand-caption { margin-top: 2px; color: #a7b8d3; font-size: 12px; letter-spacing: 0.18em; }
.auth-copy { margin-top: auto; margin-bottom: auto; padding: 32px 0; }
.auth-kicker { margin-bottom: 17px; color: #fff; font-size: clamp(2.6rem, 4.3vw, 4.6rem); font-weight: 760; letter-spacing: 0.01em; }
.auth-copy h1 { font-size: clamp(2.5rem, 4vw, 4rem); line-height: 1.15; letter-spacing: -0.03em; font-weight: 760; }
.auth-copy h1 span { color: #76d9ed; }
.auth-accent-line { width: 54px; height: 4px; margin: 25px 0 28px; border-radius: 4px; background: linear-gradient(90deg, #45e1ec, #5570ee); }
.auth-description { max-width: 440px; margin-top: 0; color: #b0c1d9; font-size: 18px; line-height: 1.75; }
.auth-feature-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.auth-feature { display: grid; grid-template-columns: 1fr; min-width: 0; gap: 4px; padding: 12px; border: 1px solid rgba(153, 203, 255, 0.2); border-radius: 14px; background: rgba(255, 255, 255, 0.07); }
.auth-feature strong, .auth-feature small { display: block; }
.auth-feature strong { margin-top: 1px; font-size: 14px; }
.auth-feature small { margin-top: 4px; color: #94a9c6; font-size: 12px; }
.auth-feature-icon { display: grid; place-items: center; width: 32px; height: 32px; margin-bottom: 4px; border-radius: 9px; font-size: 18px; font-weight: 800; }
.auth-feature-icon-blue { color: #fff; background: linear-gradient(145deg, #3c8aff, #355fe5); }
.auth-feature-icon-green { color: #fff; background: linear-gradient(145deg, #3cd0a1, #209b87); }
.auth-feature-icon-purple { color: #fff; background: linear-gradient(145deg, #9470ff, #633ed6); }
.auth-footnote { display: flex; align-items: center; gap: 12px; margin-top: 24px; color: #97abc6; font-size: 12px; letter-spacing: 0.2em; }
.auth-footnote span { width: 44px; height: 2px; background: linear-gradient(90deg, #4cdef0, #4777ef); }
.auth-form-panel { position: relative; display: flex; align-items: center; flex-direction: column; justify-content: center; padding: 64px 28px 28px; background: var(--auth-panel); }
.auth-theme-toggle { position: absolute; right: 24px; top: 16px; display: grid; place-items: center; width: 40px; height: 40px; padding: 0; border: 1px solid var(--auth-border); border-radius: 50%; background: var(--auth-toggle); color: var(--auth-text); cursor: pointer; transition: background-color 160ms ease; }
.auth-theme-toggle:hover { background: var(--auth-hover); }
.auth-theme-toggle:focus-visible { outline: 2px solid var(--auth-focus); outline-offset: 3px; }

@media (max-height: 700px) and (min-width: 801px) {
  .auth-form-panel { padding-block: 60px 16px; }
  .auth-visual { padding-block: 24px; }
  .auth-copy { padding: 20px 0; }
  .auth-kicker { font-size: 2.6rem; margin-bottom: 12px; }
  .auth-copy h1 { font-size: 2.8rem; }
  .auth-accent-line { margin: 18px 0; }
  .auth-description { font-size: 16px; }
}

@media (max-width: 800px) {
  .auth-layout { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
  .auth-visual { min-height: 0; padding: 16px 20px; }
  .brand-mark-auth { width: 40px; height: 40px; border-radius: 10px; }
  .auth-brand-name { font-size: 18px; }
  .auth-brand-caption { font-size: 11px; }
  .auth-copy, .auth-feature-row, .auth-footnote { display: none; }
  .auth-form-panel { padding: 56px 16px 20px; }
  .auth-theme-toggle { top: 10px; right: 16px; }
}

@media (max-width: 800px) and (max-height: 700px) {
  .auth-form-panel { padding-block: 48px 12px; }
}

.brand-mark img {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
