/** Design tokens ported from TravelMaster V2 — same visual language across
 *  projects, so the two read as one engineer's work rather than two demos. */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["'Bricolage Grotesque'", "sans-serif"],
        sans: ["Manrope", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
      fontSize: {
        micro: ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.04em" }],
        xs: ["0.75rem", { lineHeight: "1.1rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.9375rem", { lineHeight: "1.55rem" }],
        md: ["1.0625rem", { lineHeight: "1.65rem" }],
        lg: ["1.25rem", { lineHeight: "1.7rem" }],
        xl: ["1.5rem", { lineHeight: "1.9rem" }],
        "2xl": ["1.875rem", { lineHeight: "2.2rem" }],
        "3xl": ["2.5rem", { lineHeight: "2.7rem" }],
      },
      colors: {
        ink: {
          DEFAULT: "#12141C",
          muted: "#5B5F6E",
          faint: "#9599A6",
          inverse: "#FFFFFF",
        },
        surface: {
          DEFAULT: "#FFFFFF",
          subtle: "#F6F7FB",
          sunken: "#EEF0F6",
          raised: "#FFFFFF",
        },
        border: {
          DEFAULT: "#E4E7EF",
          strong: "#D2D6E2",
        },
        brand: {
          DEFAULT: "#2454E0",
          hover: "#1D46C4",
          active: "#17399E",
          soft: "#EEF2FF",
          softer: "#F7F9FF",
          text: "#2A4FCB",
        },
        accent: {
          teal: "#0E9F8E",
          tealSoft: "#E7F7F4",
          amber: "#C9820A",
          amberSoft: "#FBF2E1",
          green: "#178A4C",
          greenSoft: "#E9F6EE",
          red: "#D6432F",
          redSoft: "#FCEBE8",
        },
      },
      borderRadius: { xl: "1rem", "2xl": "1.25rem", "3xl": "1.75rem" },
      boxShadow: {
        soft: "0 1px 2px rgba(18,20,28,0.04), 0 1px 1px rgba(18,20,28,0.03)",
        card: "0 1px 3px rgba(18,20,28,0.05), 0 8px 24px -12px rgba(18,20,28,0.10)",
        raised: "0 4px 16px -4px rgba(18,20,28,0.12), 0 2px 6px -2px rgba(18,20,28,0.06)",
        focus: "0 0 0 4px rgba(36,84,224,0.14)",
      },
      keyframes: {
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        fadeIn: { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        pulseSoft: { "0%, 100%": { opacity: "1" }, "50%": { opacity: "0.45" } },
      },
      animation: {
        fadeUp: "fadeUp 0.5s cubic-bezier(0.16,1,0.3,1) both",
        fadeIn: "fadeIn 0.4s ease both",
        pulseSoft: "pulseSoft 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
