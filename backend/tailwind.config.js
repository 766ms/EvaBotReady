// Para reconstruir el CSS cuando cambies clases en el HTML:
//   npx tailwindcss@3.4.17 -c tailwind.config.js -i tailwind.input.css -o chat/static/chat/tailwind.css --minify
module.exports = {
  content: ["./chat/templates/**/*.html"],
  theme: { extend: {} },
  plugins: [],
};
