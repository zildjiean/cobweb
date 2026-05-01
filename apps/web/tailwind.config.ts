import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  // Severity colours are referenced via dynamic class names like
  // `text-severity-${sev}` and `bg-severity-${sev}/15`. Tailwind cannot detect
  // those at build time, so list every variant we actually use here.
  safelist: [
    "text-severity-critical", "text-severity-high", "text-severity-medium",
    "text-severity-low", "text-severity-info",
    "bg-severity-critical", "bg-severity-high", "bg-severity-medium",
    "bg-severity-low", "bg-severity-info",
    "bg-severity-critical/10", "bg-severity-high/10", "bg-severity-medium/10",
    "bg-severity-low/10", "bg-severity-info/10",
    "bg-severity-critical/15", "bg-severity-high/15", "bg-severity-medium/15",
    "bg-severity-low/15", "bg-severity-info/15",
    "bg-severity-critical/20", "bg-severity-high/20", "bg-severity-medium/20",
    "bg-severity-low/20", "bg-severity-info/20",
    "border-severity-critical/40", "border-severity-high/40", "border-severity-medium/40",
    "border-severity-low/40", "border-severity-info/40",
    "ring-severity-critical/40", "ring-severity-high/40", "ring-severity-medium/40",
    "ring-severity-low/40", "ring-severity-info/40",
  ],
  theme: {
    extend: {
      colors: {
        // Cobweb dark theme — inspired by Rapid7 InsightAppSec / Acunetix
        bg: {
          DEFAULT: "#0a0e1a",
          elevated: "#111726",
          subtle: "#0d1320",
        },
        border: {
          subtle: "#1c2436",
          DEFAULT: "#283149",
          strong: "#3a4566",
        },
        accent: {
          DEFAULT: "#6286ff",
          hover: "#7d9bff",
          subtle: "#3b5bdb",
        },
        severity: {
          critical: "#ef4444",
          high: "#f97316",
          medium: "#eab308",
          low: "#22c55e",
          info: "#64748b",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 1px 0 0 rgba(255,255,255,0.03), 0 1px 3px rgba(0,0,0,0.3)",
        "card-hover":
          "0 1px 0 0 rgba(255,255,255,0.05), 0 8px 20px -4px rgba(98,134,255,0.15)",
        glow: "0 0 0 1px rgba(98,134,255,0.4), 0 0 16px -2px rgba(98,134,255,0.5)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-right": {
          "0%": { opacity: "0", transform: "translateX(8px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-in": "fade-in 200ms ease-out",
        "slide-in-right": "slide-in-right 220ms ease-out",
        shimmer: "shimmer 1.6s linear infinite",
      },
    },
  },
  plugins: [],
};
export default config;
