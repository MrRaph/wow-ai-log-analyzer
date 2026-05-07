import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx,js,jsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // dark slate base
        bg: {
          0: "#0a0d12",
          1: "#11161c",
          2: "#161c24",
          3: "#1f2933",
        },
        accent: {
          DEFAULT: "#f59e0b", // WoW gold-ish, but generic
          fg: "#0b0d10",
          muted: "#fbbf24",
        },
        severity: {
          critical: "#ef4444",
          high: "#f97316",
          medium: "#facc15",
          low: "#38bdf8",
          info: "#94a3b8",
        },
      },
      fontFamily: {
        sans: ['"Inter"', "system-ui", "sans-serif"],
        display: ['"Cinzel"', '"Inter"', "serif"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(245, 158, 11, 0.35), 0 8px 24px -12px rgba(245,158,11,0.4)",
      },
    },
  },
  plugins: [],
};

export default config;
