/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: { extend: {} },
  // Sin "preflight": el reset de Tailwind cambiaría los estilos que ya tiene la app (App.css / index.css).
  corePlugins: { preflight: false },
  plugins: [],
}
