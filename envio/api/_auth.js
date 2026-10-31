// Login do painel: senha em ADMIN_PASSWORD, sessão em cookie assinado.
import { BlobPreconditionFailedError } from '@vercel/blob';
import { keyFor, safeEqual, signSession, verifySession } from './_crypto.js';
import { json } from './_locutores.js';

const COOKIE = 'envio_admin';
export const SESSION_MS = 12 * 60 * 60 * 1000;

const sessionKey = () => keyFor(process.env.ADMIN_SECRET, 'session');

export const isConfigured = () => Boolean(process.env.ADMIN_PASSWORD && process.env.ADMIN_SECRET);

export const checkPassword = (senha) => safeEqual(senha, process.env.ADMIN_PASSWORD);

function readCookie(request, name) {
  const header = request.headers.get('cookie') || '';
  const found = header.split(';').map((c) => c.trim()).find((c) => c.startsWith(`${name}=`));
  return found ? decodeURIComponent(found.slice(name.length + 1)) : undefined;
}

export function isAdmin(request) {
  return isConfigured() && verifySession(readCookie(request, COOKIE), sessionKey());
}

export function sessionCookie() {
  const token = signSession(Date.now() + SESSION_MS, sessionKey());
  return `${COOKIE}=${token}; Path=/api/admin; HttpOnly; Secure; SameSite=Strict; Max-Age=${SESSION_MS / 1000}`;
}

export const clearCookie = () => `${COOKIE}=; Path=/api/admin; HttpOnly; Secure; SameSite=Strict; Max-Age=0`;

/**
 * Envolve uma rota do painel: exige sessão e, pra quem altera dados, JSON
 * (formulário de outro site não consegue mandar JSON sem CORS).
 */
export function adminRoute(handler) {
  return async (request) => {
    if (!isConfigured()) return json(503, { error: 'Painel não configurado.' });
    if (!isAdmin(request)) return json(401, { error: 'Entre com a senha do painel.' });
    const isWrite = request.method !== 'GET';
    if (isWrite && !(request.headers.get('content-type') || '').startsWith('application/json')) {
      return json(415, { error: 'Envie JSON.' });
    }
    try {
      return await handler(request);
    } catch (err) {
      if (err instanceof BlobPreconditionFailedError) {
        return json(409, { error: 'O cadastro mudou enquanto você editava. Recarregue a página.' });
      }
      console.error('Erro no painel:', err);
      return json(500, { error: 'Algo deu errado. Tente de novo.' });
    }
  };
}
