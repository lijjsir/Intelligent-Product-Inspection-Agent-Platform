<template>
  <div class="auth-layout">
    <div class="auth-visual">
      <div class="auth-visual-grid" aria-hidden="true" />
      <div class="auth-brand-row">
        <div class="brand-mark brand-mark-auth" aria-label="PIAP 智能检测平台图标">
        <img src="/piap-icon.svg?v=2" alt="" width="64" height="64" />
        </div>
        <div>
          <div class="auth-brand-name">PIAP</div>
          <div class="auth-brand-caption">智能检测平台</div>
        </div>
      </div>
      <div class="auth-copy">
        <p class="auth-kicker">QUALITY INTELLIGENCE / 01</p>
        <h1>让每一次检测<br /><span>更有依据</span></h1>
        <p class="auth-description">从任务创建到稳定性评估的一体化质量检测控制台。</p>
      </div>
      <div class="auth-feature-row">
        <div class="auth-feature"><strong>实时分析</strong><span>数据洞察</span></div>
        <div class="auth-feature"><strong>风险预警</strong><span>主动识别</span></div>
        <div class="auth-feature"><strong>知识检索</strong><span>智能问答</span></div>
      </div>
      <div class="auth-footnote"><span />高效 · 智能 · 专业 · 可信</div>
    </div>
    <div class="auth-form-panel">
      <div class="auth-form-topline"><span>PIAP 控制台</span><span class="status-dot">系统在线</span></div>
      <RouterView />
      <div class="auth-copyright">© PIAP Intelligent Inspection Platform</div>
    </div>
  </div>
</template>

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
  display: grid;
  min-height: 100dvh;
  grid-template-columns: minmax(0, 1.08fr) minmax(420px, 0.92fr);
  background: #f5f8fd;
}

.auth-visual {
  position: relative;
  display: flex;
  min-height: 100%;
  flex-direction: column;
  overflow: hidden;
  padding: clamp(32px, 5vw, 72px);
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
.auth-copy { margin-top: auto; margin-bottom: auto; padding: 12vh 0 8vh; }
.auth-kicker { margin-bottom: 18px; color: #73d9e6; font-size: 11px; font-weight: 700; letter-spacing: 0.22em; }
.auth-copy h1 { font-size: clamp(2.8rem, 5vw, 5.2rem); line-height: 1.08; letter-spacing: -0.05em; font-weight: 760; }
.auth-copy h1 span { color: #78d8ea; }
.auth-description { max-width: 440px; margin-top: 24px; color: #b0c1d9; font-size: 17px; line-height: 1.8; }
.auth-feature-row { display: flex; gap: 12px; }
.auth-feature { min-width: 140px; padding: 15px 18px; border: 1px solid rgba(153, 203, 255, 0.2); border-radius: 14px; background: rgba(255, 255, 255, 0.07); backdrop-filter: blur(10px); }
.auth-feature strong, .auth-feature span { display: block; }
.auth-feature strong { font-size: 14px; }
.auth-feature span { margin-top: 4px; color: #94a9c6; font-size: 12px; }
.auth-footnote { display: flex; align-items: center; gap: 12px; margin-top: auto; color: #97abc6; font-size: 12px; letter-spacing: 0.2em; }
.auth-footnote span { width: 44px; height: 2px; background: linear-gradient(90deg, #4cdef0, #4777ef); }
.auth-form-panel { display: flex; flex-direction: column; justify-content: center; padding: clamp(24px, 6vw, 88px); background: linear-gradient(180deg, #f7faff 0%, #edf4fc 100%); }
.auth-form-topline { display: flex; justify-content: space-between; margin: 0 auto 24px; width: min(100%, 420px); color: #7285a2; font-size: 12px; letter-spacing: 0.08em; }
.status-dot { display: inline-flex; align-items: center; gap: 6px; color: #3a7a6b; }
.status-dot::before { width: 6px; height: 6px; border-radius: 50%; background: #2dbb8a; content: ""; box-shadow: 0 0 0 4px rgba(45, 187, 138, 0.12); }
.auth-copyright { width: min(100%, 420px); margin: 26px auto 0; color: #9aacbf; font-size: 11px; text-align: center; }

@media (max-width: 800px) {
  .auth-layout { grid-template-columns: 1fr; }
  .auth-visual { min-height: 380px; padding: 28px 24px; }
  .auth-copy { padding: 48px 0 36px; }
  .auth-copy h1 { font-size: 2.8rem; }
  .auth-feature-row { display: none; }
  .auth-form-panel { min-height: calc(100dvh - 380px); padding: 32px 24px; }
}

.brand-mark img {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
