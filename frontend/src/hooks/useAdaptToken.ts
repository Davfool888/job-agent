import { useEffect, useState } from "react";
import { getAuth } from "firebase/auth";

/**
 * ID token para URLs que no pueden llevar Authorization (iframes y
 * descargas directas de PDF). Devuelve:
 * - `undefined`: resolviendo (con sesión iniciada, espera antes de
 *   mostrar el iframe para no parpadear el archivo del invitado).
 * - `null`: sin sesión (invitado) o Firebase sin configurar.
 * - `string`: token listo para `?token=`.
 */
export function useAdaptToken(): string | null | undefined {
  const [token, setToken] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const user = getAuth().currentUser;
        if (!user) {
          if (alive) setToken(null);
          return;
        }
        const idToken = await user.getIdToken();
        if (alive) setToken(idToken);
      } catch {
        if (alive) setToken(null);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);
  return token;
}
