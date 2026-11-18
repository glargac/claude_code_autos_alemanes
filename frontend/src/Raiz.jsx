import { useEffect, useState } from "react";
import { api } from "./api.js";
import App from "./App.jsx";
import Login from "./Login.jsx";
import Settings from "./Settings.jsx";

// Decide qué se ve: login → (primera vez) bienvenida con las preferencias → la app.
export default function Raiz() {
  const [user, setUser] = useState(undefined); // undefined = comprobando la sesión; null = sin sesión; "sin_conexion"

  const comprobar = () => {
    setUser(undefined);
    // Un fallo de red (TypeError) no es «sesión caducada»: no hay que enseñar el login a quien solo está sin cobertura.
    api.me().then(setUser).catch((e) => setUser(e instanceof TypeError ? "sin_conexion" : null));
  };

  useEffect(() => {
    comprobar();
    const caducada = () => setUser(null);
    window.addEventListener("sesion-caducada", caducada);
    return () => window.removeEventListener("sesion-caducada", caducada);
  }, []);

  const salir = async () => {
    await api.logout().catch(() => {});
    setUser(null);
  };

  if (user === undefined) return <p className="p-6 text-slate-400">Cargando…</p>;
  if (user === "sin_conexion") {
    return (
      <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-4 p-6 text-center">
        <p className="text-lg font-semibold">Sin conexión</p>
        <p className="text-sm text-slate-400">No se pudo contactar con el servidor. Comprueba tu conexión; tu sesión sigue abierta.</p>
        <button onClick={comprobar} className="rounded-lg bg-sky-600 px-4 py-2.5 font-medium hover:bg-sky-500">Reintentar</button>
      </main>
    );
  }
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
