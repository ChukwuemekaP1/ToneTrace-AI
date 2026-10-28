/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#080C0F",
        surface: {
          DEFAULT: "#10161C",
          subtle: "#0C1115",
          elevated: "#172027",
          border: "rgba(255, 255, 255, 0.08)",
          hover: "rgba(255, 255, 255, 0.04)",
        },
        brand: {
          DEFAULT: "#10B981", // Clinical emerald
          light: "#34D399",
          dark: "#059669",
          muted: "rgba(16, 185, 129, 0.15)",
        },
        champagne: {
          DEFAULT: "#E0C39E", // Cosmetic luxury accent
          light: "#EAD5BC",
          dark: "#C7A67D",
          muted: "rgba(224, 195, 158, 0.15)",
        },
        caution: {
          DEFAULT: "#F59E0B",
          light: "#FBBF24",
          muted: "rgba(245, 158, 11, 0.15)",
        },
        adverse: {
          DEFAULT: "#EF4444",
          light: "#F87171",
          muted: "rgba(239, 68, 68, 0.15)",
        },
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      fontSize: {
        xxs: ["0.6875rem", { lineHeight: "1rem" }], // 11px
        xs: ["0.75rem", { lineHeight: "1.125rem" }], // 12px
        sm: ["0.875rem", { lineHeight: "1.25rem" }],  // 14px
        base: ["1rem", { lineHeight: "1.5rem" }],     // 16px
        lg: ["1.125rem", { lineHeight: "1.625rem" }],// 18px
        xl: ["1.25rem", { lineHeight: "1.75rem" }],   // 20px
        "2xl": ["1.5rem", { lineHeight: "2rem" }],    // 24px
      },
      borderRadius: {
        sm: "6px",
        md: "10px",
        lg: "14px",
        xl: "18px",
        "2xl": "24px",
      },
      maxWidth: {
        shell: "430px",
      },
      boxShadow: {
        glass: "0 8px 32px 0 rgba(0, 0, 0, 0.37)",
        glow: "0 0 24px rgba(16, 185, 129, 0.2)",
      },
    },
  },
  plugins: [],
};
