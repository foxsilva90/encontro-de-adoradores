// Funções puras do webhook do WhatsApp (sem I/O), separadas pra teste.
// Arquivos com "_" na frente não viram rota na Vercel.
import crypto from 'node:crypto';

const MEDIA_ID_RE = /^[0-9A-Za-z_-]{1,64}$/;

// A Meta assina o corpo bruto com HMAC-SHA256 usando o App Secret.
export function verifySignature(rawBody, header, appSecret) {
  if (!appSecret || typeof header !== 'string' || !header.startsWith('sha256=')) return false;
  const expected = crypto.createHmac('sha256', appSecret).update(rawBody).digest();
  const received = Buffer.from(header.slice('sha256='.length), 'hex');
  if (received.length !== expected.length) return false;
  return crypto.timingSafeEqual(received, expected);
}

// No Brasil a Meta às vezes entrega o número sem o nono dígito
// (55 + DDD + 8 dígitos). Gera as duas formas pra comparar.
export function phoneVariants(raw) {
  const digits = String(raw || '').replace(/\D/g, '');
  if (/^55\d{2}9\d{8}$/.test(digits)) return [digits, digits.slice(0, 4) + digits.slice(5)];
  if (/^55\d{2}\d{8}$/.test(digits)) return [digits, digits.slice(0, 4) + '9' + digits.slice(4)];
  return digits ? [digits] : [];
}

// Variável PROGRAMAS_WHATSAPP: {"5511988887777": "Nome exato da playlist"}
export function parseProgramMap(json) {
  let parsed;
  try {
    parsed = JSON.parse(json || '{}');
  } catch {
    return {};
  }
  if (!parsed || typeof parsed !== 'object') return {};
  return Object.fromEntries(
    Object.entries(parsed)
      .map(([phone, program]) => [String(phone).replace(/\D/g, ''), program])
      .filter(([phone, program]) => phone.length >= 10 && typeof program === 'string' && program.trim())
      .map(([phone, program]) => [phone, program.trim()]),
  );
}

export function findProgram(map, from) {
  for (const variant of phoneVariants(from)) {
    for (const candidate of phoneVariants(variant)) {
      if (map[candidate]) return map[candidate];
    }
  }
  return null;
}

function audioMedia(msg) {
  if (msg.type === 'audio') return msg.audio;
  if (msg.type === 'document' && /^audio\//.test(msg.document?.mime_type || '')) return msg.document;
  return null;
}

export function extractAudioMessages(body) {
  const messages = (body?.entry || [])
    .flatMap((e) => e?.changes || [])
    .flatMap((c) => c?.value?.messages || []);
  return messages
    .map((msg) => ({ msg, media: msg && audioMedia(msg) }))
    .filter(({ media }) => media && MEDIA_ID_RE.test(String(media.id || '')))
    .map(({ msg, media }) => ({ from: String(msg.from || ''), messageId: msg.id, mediaId: media.id }));
}
