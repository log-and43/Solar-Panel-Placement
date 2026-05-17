/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        rooftop: '#f59e0b',     // amber
        parking: '#3b82f6',     // blue
        offshore: '#10b981',    // emerald
      },
    },
  },
  plugins: [],
}
