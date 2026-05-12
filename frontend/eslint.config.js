import js from "@eslint/js";
import vue from "eslint-plugin-vue";
import vueParser from "vue-eslint-parser";
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";

export default [
  {
    ignores: ["dist/**", "node_modules/**", "logs/**", "coverage/**", "auto-imports.d.ts", "components.d.ts"],
  },
  js.configs.recommended,
  ...vue.configs["flat/essential"],
  {
    files: ["**/*.{js,ts,vue}"],
    languageOptions: {
      globals: {
        console: "readonly",
        document: "readonly",
        EventSource: "readonly",
        EventListener: "readonly",
        File: "readonly",
        FormData: "readonly",
        localStorage: "readonly",
        MessageEvent: "readonly",
        sessionStorage: "readonly",
        setTimeout: "readonly",
        URL: "readonly",
        window: "readonly",
      },
    },
    rules: {
      "no-undef": "off",
    },
  },
  {
    files: ["**/*.ts"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
      },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
  {
    files: ["**/*.vue"],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tsParser,
        ecmaVersion: "latest",
        sourceType: "module",
      },
    },
    rules: {
      "vue/multi-word-component-names": "off",
      "no-unused-vars": "off",
    },
  },
  {
    files: ["tests/**/*.ts"],
    languageOptions: {
      globals: {
        describe: "readonly",
        expect: "readonly",
        it: "readonly",
        vi: "readonly",
      },
    },
  },
];
