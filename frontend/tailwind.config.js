/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#18181b",
          soft: "#3f3f46",
          muted: "#71717a",
        },
        surface: {
          DEFAULT: "#ffffff",
          hover: "#fafafa",
          active: "#f4f4f5",
        },
        border: {
          DEFAULT: "#e4e4e7",
          light: "#f4f4f5",
        },
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "0.875rem" }],
      },
      borderRadius: {
        card: "0.75rem",
        container: "1rem",
      },
      boxShadow: {
        "surface-sm": "0 1px 2px rgba(0,0,0,0.04)",
        "surface-md": "0 4px 12px rgba(0,0,0,0.06)",
        "surface-lg": "0 12px 24px rgba(0,0,0,0.08)",
      },
      spacing: {
        18: "4.5rem",
      },
      fontFamily: {
        sans: ['"Noto Sans SC"', '"Source Han Sans SC"', '"Helvetica Neue"', "Arial", "sans-serif"],
      },
    },
  },
  plugins: [],
};
