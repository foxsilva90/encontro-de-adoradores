// Lê e grava o cadastro dos locutores no Vercel Blob, criptografado.
// Enquanto o painel nunca salvou nada, vale a variável CODIGOS_LOCUTORES.
//
// Cada gravação vira um arquivo novo (config/locutores-<sufixo>.enc) e o mais
// recente é o que vale. Motivo: blob público é lido pelo CDN, que guarda cópia
// velha do mesmo caminho (ignora useCache e query string). Arquivo com nome
// único nunca muda, então nunca vem velho. A lista (list) vem da API, não do CDN.
import { list, put, del, BlobPreconditionFailedError } from '@vercel/blob';
import { keyFor, encryptJson, decryptJson } from './_crypto.js';
import { configFromCodeMap, codeMapFromConfig } from './_admin.js';
import { parseCodeMap } from './_locutores.js';

// Fora de programas/: a limpeza diária (api/limpar.js) não toca aqui.
export const CONFIG_BASE = 'config/locutores.enc';
export const VERSION_PREFIX = 'config/locutores-';
// Versão antiga, de antes dos arquivos versionados: lida uma vez pra migrar.
const LEGACY_PATH = 'config/locutores.enc';
const KEEP_VERSIONS = 10;

function configKey() {
  const secret = process.env.ADMIN_SECRET;
  if (!secret) throw new Error('ADMIN_SECRET não configurado');
  return keyFor(secret, 'config');
}

const blobDeps = { listFn: list, putFn: put, delFn: del, fetchFn: fetch };

/** Versões salvas, da mais nova pra mais velha. */
async function versions({ listFn }) {
  const { blobs } = await listFn({ prefix: 'config/', limit: 1000 });
  return blobs
    .filter((b) => b.pathname.startsWith(VERSION_PREFIX))
    .sort((a, b) => new Date(b.uploadedAt) - new Date(a.uploadedAt));
}

async function fetchConfig(url, fetchFn) {
  const resp = await fetchFn(url, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`Falha ao ler o cadastro: ${resp.status}`);
  return decryptJson(await resp.text(), configKey());
}

async function initialConfig({ listFn, fetchFn }) {
  const { blobs } = await listFn({ prefix: LEGACY_PATH, limit: 1 });
  const legacy = blobs.find((b) => b.pathname === LEGACY_PATH);
  if (legacy) return fetchConfig(legacy.url, fetchFn);
  return configFromCodeMap(parseCodeMap(process.env.CODIGOS_LOCUTORES));
}

/**
 * @returns {Promise<{config: object, etag: string | null}>}
 * etag = caminho da versão lida (null = painel ainda não salvou nada).
 */
export async function readConfig(deps = blobDeps) {
  const [latest] = await versions(deps);
  if (!latest) return { config: await initialConfig(deps), etag: null };
  return { config: await fetchConfig(latest.url, deps.fetchFn), etag: latest.pathname };
}

/** Grava só se ninguém salvou outra versão depois da leitura (etag). */
export async function writeConfig(config, etag, deps = blobDeps) {
  const before = await versions(deps);
  if ((before[0]?.pathname ?? null) !== etag) throw new BlobPreconditionFailedError();
  const result = await deps.putFn(CONFIG_BASE, encryptJson(config, configKey()), {
    access: 'public',
    addRandomSuffix: true,
    contentType: 'application/octet-stream',
  });
  const old = before.slice(KEEP_VERSIONS - 1).map((b) => b.url);
  if (old.length) await deps.delFn(old).catch((err) => console.error('Falha ao limpar versões antigas:', err));
  return result.pathname;
}

/** Painel: na primeira vez, salva o cadastro inicial pra os ids ficarem fixos. */
export async function readConfigForAdmin(deps = blobDeps) {
  const current = await readConfig(deps);
  if (current.etag) return current;
  const etag = await writeConfig(current.config, null, deps);
  return { config: current.config, etag };
}

export async function loadLocutorMap() {
  const { config } = await readConfig();
  return codeMapFromConfig(config);
}
