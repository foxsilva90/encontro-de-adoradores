const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const FROM_EMAIL = 'Rádio Encontro de Adoradores <devocional@encontrodeadoradores.com>';
const COMMUNITY_LINK = 'https://whatsapp.com/channel/0029VbDQwyoIXnlxtiOuSN2R';
const LOGO_URL = 'https://encontrodeadoradores.com/logo_tunein_1200x1200.jpg';

function toE164(whatsapp) {
  if (!whatsapp) return undefined;
  const digits = whatsapp.replace(/\D/g, '');
  if (!digits) return undefined;
  return `+${digits.startsWith('55') ? digits : `55${digits}`}`;
}

function welcomeEmailHtml(nome) {
  return `
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; color: #1a1a1a;">
      <div style="text-align:center;margin-bottom:16px;"><img src="${LOGO_URL}" alt="Encontro de Adoradores" width="80" height="80" style="border-radius:50%;"></div>
      <h2 style="color: #0D2A4A;">Bem-vindo(a), ${nome}!</h2>
      <p>Você está cadastrado(a) para receber o devocional diário da Rádio Encontro de Adoradores por e-mail. 🙏</p>
      <p>Entre também na nossa comunidade do WhatsApp para acompanhar novidades:</p>
      <p><a href="${COMMUNITY_LINK}" style="background:#0D2A4A;color:#fff;padding:10px 18px;border-radius:6px;text-decoration:none;display:inline-block;">Entrar na comunidade</a></p>
      <p style="margin-top:24px;font-size:13px;color:#666;">Rádio Encontro de Adoradores</p>
    </div>
  `;
}

async function insertSubscriber(nome, email, whatsapp) {
  const url = `${process.env.SUPABASE_URL}/rest/v1/devocional_subscribers`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      apikey: process.env.SUPABASE_ANON_KEY,
      Authorization: `Bearer ${process.env.SUPABASE_ANON_KEY}`,
      Prefer: 'return=minimal',
    },
    body: JSON.stringify({ nome, email, whatsapp: whatsapp || null }),
  });
  return response;
}

async function addToReach(nome, email, whatsapp) {
  const token = process.env.HOSTINGER_API_TOKEN;
  if (!token) return;

  try {
    await fetch('https://developers.hostinger.com/api/reach/v1/contacts', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        email,
        name: nome,
        phone: toE164(whatsapp),
      }),
    });
  } catch (err) {
    // Best-effort: Reach é só uma cópia dos contatos pra campanhas manuais.
    // Falha aqui não pode derrubar o cadastro principal (Supabase + e-mail).
  }
}

async function sendWelcomeEmail(nome, email) {
  await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
    },
    body: JSON.stringify({
      from: FROM_EMAIL,
      to: email,
      subject: 'Bem-vindo(a) ao Devocional Diário 🙏',
      html: welcomeEmailHtml(nome),
    }),
  });
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ error: 'Method not allowed' });
  }

  if (!process.env.SUPABASE_URL || !process.env.SUPABASE_ANON_KEY || !process.env.RESEND_API_KEY) {
    return res.status(503).json({ error: 'Serviço indisponível' });
  }

  const { nome, email, whatsapp } = req.body || {};

  if (typeof nome !== 'string' || nome.trim().length < 2) {
    return res.status(400).json({ error: 'Nome inválido' });
  }
  if (typeof email !== 'string' || !EMAIL_RE.test(email.trim())) {
    return res.status(400).json({ error: 'E-mail inválido' });
  }
  if (whatsapp !== undefined && whatsapp !== null && typeof whatsapp !== 'string') {
    return res.status(400).json({ error: 'WhatsApp inválido' });
  }

  const cleanNome = nome.trim();
  const cleanEmail = email.trim().toLowerCase();
  const cleanWhatsapp = whatsapp ? whatsapp.trim() : null;

  try {
    const dbResponse = await insertSubscriber(cleanNome, cleanEmail, cleanWhatsapp);

    if (dbResponse.status === 409) {
      return res.status(200).json({ ok: true, alreadyRegistered: true });
    }
    if (!dbResponse.ok) {
      return res.status(502).json({ error: 'Falha ao salvar cadastro' });
    }

    await sendWelcomeEmail(cleanNome, cleanEmail);
    await addToReach(cleanNome, cleanEmail, cleanWhatsapp);

    return res.status(200).json({ ok: true });
  } catch (err) {
    return res.status(502).json({ error: 'Falha ao processar cadastro' });
  }
}
