import { useState } from "react";
import { api } from "./api.js";

const input =
  "w-full rounded-lg bg-slate-950 px-3 py-2.5 text-base ring-1 ring-slate-700 focus:outline-none focus:ring-sky-500";

export default function Login({ onLogin }) {
  const [usuario, setUsuario] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const enviar = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogin(await api.login(usuario.trim(), password));
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center p-6">
      <h1 className="text-2xl font-bold">Autos Alemanes</h1>
      <p className="mb-6 text-slate-400">Costa del Sol · inicia sesión para continuar</p>
      <form onSubmit={enviar} className="space-y-4 rounded-xl bg-slate-900 p-5 ring-1 ring-slate-800">
        <label className="block text-sm">
          <span className="mb-1 block text-slate-400">Usuario</span>
          <input className={input} autoFocus autoComplete="username" autoCapitalize="none" value={usuario} onChange={(e) => setUsuario(e.target.value)} />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-400">Contraseña</span>
          <input type="password" className={input} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p className="rounded-lg bg-red-950 px-3 py-2 text-sm text-red-300">{error}</p>}
        <button disabled={busy || !usuario.trim() || !password} className="w-full rounded-lg bg-sky-600 px-4 py-2.5 font-medium hover:bg-sky-500 disabled:opacity-50">
          {busy ? "Entrando…" : "Entrar"}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-slate-500">Las cuentas las crea el administrador.</p>
    </main>
  );
}
