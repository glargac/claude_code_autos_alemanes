import { useEffect, useState } from "react";
import { api } from "./api.js";
import App from "./App.jsx";
import Login from "./Login.jsx";
import Settings from "./Settings.jsx";

// Decide qué se ve: login → (primera vez) bienvenida con las preferencias → la app.
export default function Raiz() {
  const [user, setUser] = useState(undefined); // undefined = comprobando la sesión; null = sin sesión

  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null));
    const caducada = () => setUser(null);
    window.addEventListener("sesion-caducada", caducada);
    return () => window.removeEventListener("sesion-caducada", caducada);
  }, []);

  const salir = async () => {
    await api.logout().catch(() => {});
    setUser(null);
  };

  if (user === undefined) return <p className="p-6 text-slate-400">Cargando…</p>;
  if (user === null) return <Login onLogin={setUser} />;
  if (!user.configurado) return <Bienvenida user={user} onSalir={salir} onListo={() => setUser({ ...user, configurado: true })} />;
  return <App key={user.usuario} user={user} onSalir={salir} />;
}

// Primera entrada: el usuario elige sus preferencias y, al aceptar, empieza su sincronización.
function Bienvenida({ user, onSalir, onListo }) {
  return (
    <main className="mx-auto max-w-4xl space-y-4 p-6">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Bienvenido, {user.usuario}</h1>
          <p className="text-sm text-slate-400">
            Elige qué coches quieres buscar y cómo puntuarlos. Al aceptar empieza la primera sincronización (puede tardar
            30-40 minutos; ya podrás usar la app mientras tanto). Podrás cambiarlo cuando quieras en Ajustes.
          </p>
        </div>
        <button onClick={onSalir} className="shrink-0 text-sm text-slate-400 hover:text-white">Salir</button>
      </header>
      <Settings onboarding onRun={async () => { await api.sync(); onListo(); }} syncRunning={false} />
    </main>
  );
}
