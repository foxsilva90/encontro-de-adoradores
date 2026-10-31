// Regras puras do link de envio (sem I/O), separadas pra teste.
import crypto from 'node:crypto';

export const UPLOAD_PREFIX = 'programas/';
export const MAX_UPLOAD_BYTES = 500 * 1024 * 1024;
export const TEMP_FILE_TTL_MS = 24 * 60 * 60 * 1000;
export const ALLOWED_CONTENT_TYPES = ['audio/*', 'video/mp4', 'video/quicktime', 'application/octet-stream'];

const MIN_CODE_LENGTH = 8;
const MAX_CODE_LENGTH = 64;
const BLOB_HOST_RE = /^[a-z0-9]+\.public\.blob\.vercel-storage\.com$/;

const normalizeCode = (code) => String(code ?? '').trim().toUpperCase();

/**
 * Variável CODIGOS_LOCUTORES: {"MANHA-7K2P9QX4": "Nome exato da playlist"}
 * @param {string | undefined} json
 * @returns {Record<string, string>}
 */
export function parseCodeMap(json) {
  let parsed;
  try {
    parsed = JSON.parse(json || '{}');
  } catch {
    return {};
  }
  if (!parsed || typeof parsed !== 'object') return {};
  return Object.fromEntries(
    Object.entries(parsed)
      .map(([code, program]) => [normalizeCode(code), typeof program === 'string' ? program.trim() : ''])
      .filter(([code, program]) => code.length >= MIN_CODE_LENGTH && code.length <= MAX_CODE_LENGTH && program),
  );
}

/**
 * Compara em tempo constante pra não vazar o código por tempo de resposta.
 * @returns {string | null} nome do programa
 */
export function findProgramByCode(map, code) {
  const wanted = Buffer.from(normalizeCode(code));
  if (wanted.length < MIN_CODE_LENGTH || wanted.length > MAX_CODE_LENGTH) return null;
  let found = null;
  for (const [candidate, program] of Object.entries(map)) {
    const buf = Buffer.from(candidate);
    if (buf.length === wanted.length && crypto.timingSafeEqual(buf, wanted)) found = program;
  }
  return found;
}

export function isOurBlobUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === 'https:' && BLOB_HOST_RE.test(u.hostname) && u.pathname.startsWith('/' + UPLOAD_PREFIX);
  } catch {
    return false;
  }
}

export function isAllowedUploadPath(pathname) {
  return typeof pathname === 'string' && pathname.startsWith(UPLOAD_PREFIX) && !pathname.includes('..');
}

export function isExpired(uploadedAt, now = Date.now()) {
  return now - new Date(uploadedAt).getTime() > TEMP_FILE_TTL_MS;
}

export function json(status, body) {
  return Response.json(body, { status, headers: { 'Cache-Control': 'no-store' } });
}
