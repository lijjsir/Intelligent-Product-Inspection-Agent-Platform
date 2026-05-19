import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";

import "element-plus/theme-chalk/el-overlay.css";
import "element-plus/theme-chalk/el-message-box.css";
import "element-plus/theme-chalk/el-message.css";

import "./styles/index.css";

const app = createApp(App);

app.use(createPinia());
app.use(router);
app.mount("#app");
