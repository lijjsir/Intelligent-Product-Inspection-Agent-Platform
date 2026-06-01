import { defineConfig, loadEnv, type Plugin, type ViteDevServer } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";
import AutoImport from "unplugin-auto-import/vite";
import Components from "unplugin-vue-components/vite";
import { ElementPlusResolver } from "unplugin-vue-components/resolvers";

function langfuseLegacyRedirect(): Plugin {
  return {
    name: "langfuse-legacy-redirect",
    configureServer(server: ViteDevServer) {
      server.middlewares.use((req, res, next) => {
        const url = req.url || "";
        if (url.startsWith("/langfuse/project/")) {
          res.statusCode = 302;
          res.setHeader("Location", url.replace(/^\/langfuse/, ""));
          res.end();
          return;
        }
        next();
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendTarget = env.VITE_PROXY_TARGET || "http://localhost:8000";
  const langfuseTarget = env.VITE_LANGFUSE_PROXY_TARGET || "http://127.0.0.1:3000";
  const langfuseProxy = {
    target: langfuseTarget,
    changeOrigin: true,
  };

  return {
    plugins: [
      langfuseLegacyRedirect(),
      vue(),
      AutoImport({
        resolvers: [ElementPlusResolver()],
      }),
      Components({
        resolvers: [ElementPlusResolver()],
      }),
    ],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes("node_modules")) {
              return;
            }
            if (id.includes("echarts")) {
              return "vendor-echarts";
            }
            if (id.includes("element-plus") || id.includes("@element-plus")) {
              return "vendor-element-plus";
            }
            if (id.includes("vue") || id.includes("pinia") || id.includes("vue-router")) {
              return "vendor-vue";
            }
            return "vendor-misc";
          },
        },
      },
      chunkSizeWarningLimit: 900,
    },
    server: {
      port: 5173,
      host: true,
      watch: {
        usePolling: true,
        interval: 1000,
      },
      proxy: {
        "/_next": langfuseProxy,
        "/api/auth": langfuseProxy,
        "/api/public": langfuseProxy,
        "/api/trpc": langfuseProxy,
        "/auth": langfuseProxy,
        "/icon.svg": langfuseProxy,
        "/project": langfuseProxy,
        "/api": {
          target: backendTarget,
          changeOrigin: true,
        },
        "/uploads": {
          target: backendTarget,
          changeOrigin: true,
        },
        "/langfuse": {
          target: langfuseTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/langfuse/, ""),
        },
      },
    },
  };
});
