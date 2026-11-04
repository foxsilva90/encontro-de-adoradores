// Troca a senha do painel com o token do e-mail de recuperação e já entra.
import { isConfigured, sessionCookie } from '../_auth.js';
import { json } from '../_locutores.js';
import {
  readStoredPassword, writeStoredPassword, passwordMark, verifyResetToken, validateNewPassword,
} from '../_password.js';

const FAIL_DELAY_MS = 800;

export async function POST(request) {
  if (!isConfigured()) return json(503, { error: 'Painel não configurado.' });
  if (!(request.headers.get('content-type') || '').startsWith('application/json')) {
    return json(415, { error: 'Envie JSON.' });
  }
  const body = await request.json().catch(() => ({}));
  try {
    if (!verifyResetToken(body.token, passwordMark(await readStoredPassword()))) {
      await new Promise((r) => setTimeout(r, FAIL_DELAY_MS));
      return json(400, { error: 'Link inválido ou vencido. Peça um novo em "Esqueci a senha".' });
    }
    const problema = validateNewPassword(body.senha);
    if (problema) return json(400, { error: problema });
    await writeStoredPassword(body.senha);
  } catch (err) {
    console.error('Falha ao redefinir a senha:', err);
    return json(500, { error: 'Algo deu errado. Tente de novo.' });
  }
  const resp = json(200, { ok: true });
  resp.headers.set('Set-Cookie', sessionCookie());
  return resp;
}
