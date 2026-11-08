import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { 50: "#eef4ff", 100: "#dbe7ff", 500: "#3b6cf6", 600: "#2953e0", 700: "#1f3fb5", 900: "#13224f" },
      },
    },
  },
  plugins: [],
} satisfies Config;
