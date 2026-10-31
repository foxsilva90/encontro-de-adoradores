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

const cleanStr = (v) => (typeof v === 'string' ? v.trim() : '');
const cleanList = (v) => (Array.isArray(v) ? v.map(cleanStr).filter(Boolean) : []);

/**
 * Normaliza um cadastro. Formatos aceitos em CODIGOS_LOCUTORES:
 *   "CODIGO": "Nome da playlist"
 *   "CODIGO": {"programa": "Nome", "playlists": ["P1", "P2"]}          (1 envio → várias playlists)
 *   "CODIGO": {"programa": "Nome", "destinos": [{"nome": "Segunda", "playlists": ["P1"]}, ...]}
 * @returns {{programa: string, destinos: {nome: string, playlists: string[]}[]} | null}
 */
function normalizeEntry(value) {
  if (typeof value === 'string') {
    const name = value.trim();
    return name ? { programa: name, destinos: [{ nome: name, playlists: [name] }] } : null;
  }
  if (!value || typeof value !== 'object') return null;
  const programa = cleanStr(value.programa);
  if (!programa) return null;
  const destinos = Array.isArray(value.destinos)
    ? value.destinos
        .map((d) => ({ nome: cleanStr(d?.nome), playlists: cleanList(d?.playlists) }))
        .filter((d) => d.nome && d.playlists.length)
    : [{ nome: programa, playlists: cleanList(value.playlists) }].filter((d) => d.playlists.length);
  return destinos.length ? { programa, destinos } : null;
}

/** @param {string | undefined} json */
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
      .map(([code, value]) => [normalizeCode(code), normalizeEntry(value)])
      .filter(([code, entry]) => code.length >= MIN_CODE_LENGTH && code.length <= MAX_CODE_LENGTH && entry),
  );
}

/** Compara em tempo constante pra não vazar o código por tempo de resposta. */
export function findLocutorByCode(map, code) {
  const wanted = Buffer.from(normalizeCode(code));
  if (wanted.length < MIN_CODE_LENGTH || wanted.length > MAX_CODE_LENGTH) return null;
  let found = null;
  for (const [candidate, entry] of Object.entries(map)) {
    const buf = Buffer.from(candidate);
    if (buf.length === wanted.length && crypto.timingSafeEqual(buf, wanted)) found = entry;
  }
  return found;
}

/**
 * Escolhe o destino do envio. Com um destino só, o título é o nome do
 * programa; com vários (ex.: dias da semana), "Programa - Dia".
 * @returns {{titulo: string, playlists: string[]} | null}
 */
export function resolveDestino(locutor, index) {
  if (!locutor || !Number.isInteger(index)) return null;
  const destino = locutor.destinos[index];
  if (!destino) return null;
  const titulo = locutor.destinos.length > 1 ? `${locutor.programa} - ${destino.nome}` : locutor.programa;
  return { titulo, playlists: destino.playlists };
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
