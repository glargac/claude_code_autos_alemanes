import React from "react";
import { createRoot } from "react-dom/client";
import Raiz from "./Raiz.jsx";
import "./index.css";

createRoot(document.getElementById("root")).render(<Raiz />);

// PWA: instalable desde el navegador. Solo en la versión compilada (en desarrollo, el service worker estorba).
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}
