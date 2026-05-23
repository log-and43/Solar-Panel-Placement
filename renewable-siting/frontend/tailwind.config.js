/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Dark satellite palette borrowed from the Codex version.
        bg:     '#101414',
        panel:  '#181f1e',
        panel2: '#202927',
        line:   '#31403b',
        muted:  '#a7b8ae',
        text:   '#eef5f0',
        // Category accents (also used in the map and legend).
        rooftop:  '#67d391',  // green
        parking:  '#f5c45b',  // yellow
        ocean:    '#53c7df',  // cyan
        wind:     '#6ea2ff',  // blue
        rose:     '#ee7b78',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system',
               'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
