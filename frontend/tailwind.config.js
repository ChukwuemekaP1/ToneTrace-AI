/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#F7F8F6",
        surface: {
          DEFAULT: "#FFFFFF",
          subtle: "#F9FAFB",
          elevated: "#FFFFFF",
          border: "#E5E7EB",
          hover: "#F3F4F6",
        },
        brand: {
          DEFAULT: "#3D6B58", // Botanical sage green
          light: "#527E6A",
          dark: "#2A4B3D",
          muted: "#EAF2ED",
        },
        charcoal: {
          DEFAULT: "#181E24", // Premium dark focal element (health report pills, scan button)
          light: "#262E35",
          muted: "#F0F2F4",
        },
        autumn: {
          terracotta: "#C87D65",
          sand: "#EFE8E2",
          rose: "#D9A5A5",
          olive: "#6C7A68",
          slate: "#64748B",
        },
        champagne: {
          DEFAULT: "#D8BC97", // Warm porcelain luxury accent
          light: "#EADCC9",
          dark: "#B8966E",
          muted: "rgba(216, 188, 151, 0.18)",
        },
        caution: {
          DEFAULT: "#D97706",
          light: "#F59E0B",
          muted: "rgba(245, 158, 11, 0.12)",
        },
        adverse: {
          DEFAULT: "#DC2626",
          light: "#EF4444",
          muted: "rgba(239, 68, 68, 0.12)",
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
