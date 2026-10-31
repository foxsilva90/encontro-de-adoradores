// Criptografia do cadastro (AES-256-GCM) e sessão do painel (HMAC).
// As duas chaves saem de ADMIN_SECRET, separadas por propósito (HKDF).
import crypto from 'node:crypto';

const IV_BYTES = 12;
const TAG_BYTES = 16;
const SALT = 'envio-programas';

/** @returns {Buffer} chave de 32 bytes pro propósito informado */
export function keyFor(secret, purpose) {
  return Buffer.from(crypto.hkdfSync('sha256', String(secret), SALT, purpose, 32));
}

export function encryptJson(value, key) {
  const iv = crypto.randomBytes(IV_BYTES);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  const body = Buffer.concat([cipher.update(JSON.stringify(value), 'utf8'), cipher.final()]);
  return Buffer.concat([iv, cipher.getAuthTag(), body]).toString('base64');
}

/** Lança erro se a chave estiver errada ou o conteúdo tiver sido alterado. */
export function decryptJson(text, key) {
  const raw = Buffer.from(String(text), 'base64');
  const iv = raw.subarray(0, IV_BYTES);
  const tag = raw.subarray(IV_BYTES, IV_BYTES + TAG_BYTES);
  const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv);
  decipher.setAuthTag(tag);
  const body = Buffer.concat([decipher.update(raw.subarray(IV_BYTES + TAG_BYTES)), decipher.final()]);
  return JSON.parse(body.toString('utf8'));
}

const mac = (text, key) => crypto.createHmac('sha256', key).update(text).digest('base64url');

/** Compara em tempo constante, inclusive textos de tamanhos diferentes. */
export function safeEqual(a, b) {
  const sa = String(a ?? '');
  const sb = String(b ?? '');
  if (!sa || !sb) return false;
  const ha = crypto.createHash('sha256').update(sa).digest();
  const hb = crypto.createHash('sha256').update(sb).digest();
  return crypto.timingSafeEqual(ha, hb) && sa.length === sb.length;
}

export function signSession(expiresAt, key) {
  const exp = String(Math.floor(expiresAt));
  return `${exp}.${mac(exp, key)}`;
}

export function verifySession(token, key, now = Date.now()) {
  if (typeof token !== 'string') return false;
  const [exp, signature, extra] = token.split('.');
  if (!exp || !signature || extra !== undefined || !/^\d+$/.test(exp)) return false;
  return safeEqual(signature, mac(exp, key)) && Number(exp) > now;
}
