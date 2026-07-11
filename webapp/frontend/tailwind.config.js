/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // NNPC green accent
        accent: {
          DEFAULT: '#00843D',   // NNPC green
          glow:    '#009E4A',   // hover
          dim:     '#00632E',   // deep
          light:   '#E7F3EC',   // tint background
        },
        // amber retained ONLY for semantic warning / MEDIUM confidence
        amber: { DEFAULT: '#E5A445', dim: '#8B6326', glow: '#FBE4B8' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        display: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'Monaco', 'monospace'],
      },
    },
  },
  plugins: [],
};
