import { isConfigured, checkPassword, sessionCookie, clearCookie } from '../_auth.js';
import { json } from '../_locutores.js';

const FAIL_DELAY_MS = 800;

export async function POST(request) {
  if (!isConfigured()) return json(503, { error: 'Painel não configurado.' });
  const body = await request.json().catch(() => ({}));
  let ok;
  try {
    ok = await checkPassword(body.senha);
  } catch (err) {
    console.error('Falha ao conferir a senha:', err);
    return json(500, { error: 'Algo deu errado. Tente de novo.' });
  }
  if (!ok) {
    await new Promise((r) => setTimeout(r, FAIL_DELAY_MS));
    return json(401, { error: 'Senha incorreta.' });
  }
  const resp = json(200, { ok: true });
  resp.headers.set('Set-Cookie', sessionCookie());
  return resp;
}

export async function DELETE() {
  const resp = json(200, { ok: true });
  resp.headers.set('Set-Cookie', clearCookie());
  return resp;
}
