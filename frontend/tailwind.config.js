/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: "#0f172a",
          secondary: "#4f46e5",
          accent: "#10b981",
          background: "#f8fafc",
        },
      },
      fontFamily: {
        sans: ["Helvetica", "Arial", "sans-serif"],
      },
      boxShadow: {
        soft: "0 20px 45px -25px rgba(15, 23, 42, 0.28)",
      },
      backgroundImage: {
        mesh: "radial-gradient(circle at top left, rgba(79, 70, 229, 0.10), transparent 28%), radial-gradient(circle at bottom right, rgba(16, 185, 129, 0.10), transparent 25%)",
      },
    },
  },
  plugins: [],
};
