// Senha do painel e recuperação por e-mail.
//
// Enquanto ninguém redefiniu, vale ADMIN_PASSWORD. Depois de um "esqueci a
// senha", a nova senha fica no Blob como hash scrypt, criptografado, em arquivo
// versionado (config/senha-<sufixo>.enc; o mais recente vale — mesmo motivo do
// _store.js: o CDN devolve cópia velha de caminho repetido).
//
// O link de recuperação leva um token "exp.marca.assinatura". A marca é tirada
// da senha atual, então o link morre assim que a senha muda (uso único).
import crypto from 'node:crypto';
import { list, put, del } from '@vercel/blob';
import { keyFor, encryptJson, decryptJson, safeEqual } from './_crypto.js';

export const PASSWORD_PREFIX = 'config/senha-';
export const RESET_TTL_MS = 30 * 60 * 1000;
export const MIN_PASSWORD_LENGTH = 10;
export const MAX_PASSWORD_LENGTH = 200;
const KEEP_VERSIONS = 3;
const SCRYPT_KEYLEN = 32;

const secret = () => process.env.ADMIN_SECRET;
const storeKey = () => keyFor(secret(), 'password');
const resetKey = () => keyFor(secret(), 'reset');

const blobDeps = { listFn: list, putFn: put, delFn: del, fetchFn: fetch };

// ------------------------------------------------------------ hash

export function hashPassword(senha) {
  const salt = crypto.randomBytes(16);
  const hash = crypto.scryptSync(String(senha), salt, SCRYPT_KEYLEN);
  return `scrypt$${salt.toString('base64')}$${hash.toString('base64')}`;
}

export function verifyHash(senha, stored) {
  const [kind, salt, hash] = String(stored ?? '').split('$');
  if (kind !== 'scrypt' || !salt || !hash || typeof senha !== 'string' || !senha) return false;
  const expected = Buffer.from(hash, 'base64');
  const got = crypto.scryptSync(senha, Buffer.from(salt, 'base64'), expected.length);
  return crypto.timingSafeEqual(got, expected);
}

export function validateNewPassword(senha) {
  if (typeof senha !== 'string' || senha.length < MIN_PASSWORD_LENGTH) {
    return `A senha precisa ter pelo menos ${MIN_PASSWORD_LENGTH} caracteres.`;
  }
  if (senha.length > MAX_PASSWORD_LENGTH) return 'Senha longa demais.';
  return null;
}

// ------------------------------------------------------------ armazenamento

async function versions({ listFn }) {
  const { blobs } = await listFn({ prefix: PASSWORD_PREFIX, limit: 100 });
  return blobs.sort((a, b) => new Date(b.uploadedAt) - new Date(a.uploadedAt));
}

/** @returns {Promise<{hash: string, version: string} | null>} null = vale ADMIN_PASSWORD */
export async function readStoredPassword(deps = blobDeps) {
  const [latest] = await versions(deps);
  if (!latest) return null;
  const resp = await deps.fetchFn(latest.url, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`Falha ao ler a senha: ${resp.status}`);
  const { hash } = decryptJson(await resp.text(), storeKey());
  return { hash, version: latest.pathname };
}

export async function writeStoredPassword(senha, deps = blobDeps) {
  const before = await versions(deps);
  await deps.putFn(`${PASSWORD_PREFIX}v.enc`, encryptJson({ hash: hashPassword(senha) }, storeKey()), {
    access: 'public',
    addRandomSuffix: true,
    contentType: 'application/octet-stream',
  });
  const old = before.slice(KEEP_VERSIONS - 1).map((b) => b.url);
  if (old.length) await deps.delFn(old).catch((err) => console.error('Falha ao limpar senhas antigas:', err));
}

/** Confere a senha digitada contra a salva no Blob ou, se não houver, ADMIN_PASSWORD. */
export async function checkPassword(senha, deps = blobDeps) {
  const stored = await readStoredPassword(deps);
  return stored ? verifyHash(senha, stored.hash) : safeEqual(senha, process.env.ADMIN_PASSWORD);
}

// ------------------------------------------------------------ token de recuperação

/** Marca curta da senha vigente: muda quando a senha muda. */
export function passwordMark(stored) {
  const base = stored ? stored.version : `env:${process.env.ADMIN_PASSWORD ?? ''}`;
  return crypto.createHmac('sha256', resetKey()).update(`mark:${base}`).digest('base64url').slice(0, 16);
}

const sign = (text) => crypto.createHmac('sha256', resetKey()).update(text).digest('base64url');

export function signResetToken(mark, now = Date.now()) {
  const payload = `${Math.floor(now + RESET_TTL_MS)}.${mark}`;
  return `${payload}.${sign(payload)}`;
}

export function verifyResetToken(token, mark, now = Date.now()) {
  if (typeof token !== 'string') return false;
  const parts = token.split('.');
  if (parts.length !== 3 || !/^\d+$/.test(parts[0])) return false;
  const [exp, tokenMark, signature] = parts;
  return safeEqual(signature, sign(`${exp}.${tokenMark}`))
    && safeEqual(tokenMark, mark)
    && Number(exp) > now;
}
