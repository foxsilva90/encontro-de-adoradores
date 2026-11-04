// "Esqueci a senha": manda um link de redefinição pro ADMIN_EMAIL (Resend).
// Sempre responde a mesma coisa, pra não revelar nada a quem não é o admin.
import { isConfigured } from '../_auth.js';
import { json } from '../_locutores.js';
import { readStoredPassword, passwordMark, signResetToken, RESET_TTL_MS } from '../_password.js';

const COOLDOWN_MS = 2 * 60 * 1000;
const PANEL_URL = 'https://envio.encontrodeadoradores.com/admin.html';
const FROM_EMAIL = 'Rádio Encontro de Adoradores <devocional@encontrodeadoradores.com>';
const RESPOSTA = { ok: true, message: 'Se o e-mail do painel estiver configurado, o link de redefinição chega em instantes.' };

let lastSentAt = 0;

function emailHtml(link) {
  const minutos = RESET_TTL_MS / 60000;
  return `<p>Alguém pediu pra redefinir a senha do <b>Painel de Locutores</b>.</p>
<p><a href="${link}">Clique aqui pra criar uma nova senha</a> (vale por ${minutos} minutos e só uma vez).</p>
<p>Se não foi você, ignore este e-mail: a senha atual continua valendo.</p>`;
}

async function sendResetEmail(to, link) {
  const resp = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${process.env.RESEND_API_KEY}` },
    body: JSON.stringify({
      from: process.env.RESET_FROM_EMAIL || FROM_EMAIL,
      to,
      subject: 'Redefinir a senha do Painel de Locutores',
      html: emailHtml(link),
    }),
  });
  if (!resp.ok) throw new Error(`Resend respondeu ${resp.status}: ${await resp.text()}`);
}

export async function POST(request) {
  if (!(request.headers.get('content-type') || '').startsWith('application/json')) {
    return json(415, { error: 'Envie JSON.' });
  }
  const to = process.env.ADMIN_EMAIL;
  if (!isConfigured() || !to || !process.env.RESEND_API_KEY) {
    console.error('Recuperação de senha sem ADMIN_EMAIL/RESEND_API_KEY configurados.');
    return json(200, RESPOSTA);
  }
  if (Date.now() - lastSentAt < COOLDOWN_MS) return json(200, RESPOSTA);
  lastSentAt = Date.now();
  try {
    const token = signResetToken(passwordMark(await readStoredPassword()));
    await sendResetEmail(to, `${process.env.PANEL_URL || PANEL_URL}#reset=${encodeURIComponent(token)}`);
  } catch (err) {
    lastSentAt = 0;
    console.error('Falha ao enviar e-mail de recuperação:', err);
    return json(502, { error: 'Não consegui enviar o e-mail agora. Tente de novo em instantes.' });
  }
  return json(200, RESPOSTA);
}
