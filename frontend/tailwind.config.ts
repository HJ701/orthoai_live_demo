import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          ink: "#1f2937",
          muted: "#6b7280",
          line: "#e5e7eb",
          primary: "#6366f1",
          primaryDark: "#4f46e5",
          secondary: "#8b5cf6",
          secondaryDark: "#7c3aed",
          bg: "#f8fafc",
        },
      },
      boxShadow: {
        panel: "0 4px 20px rgba(0, 0, 0, 0.08)",
      },
      borderRadius: {
        app: "20px",
      },
    },
  },
  plugins: [],
};

export default config;
