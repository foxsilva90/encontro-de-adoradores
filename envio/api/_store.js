// Lê e grava o cadastro dos locutores no Vercel Blob, criptografado.
// Enquanto o painel nunca salvou nada, vale a variável CODIGOS_LOCUTORES.
import { get, put } from '@vercel/blob';
import { keyFor, encryptJson, decryptJson } from './_crypto.js';
import { configFromCodeMap, codeMapFromConfig } from './_admin.js';
import { parseCodeMap } from './_locutores.js';

// Fora de programas/: a limpeza diária (api/limpar.js) não toca aqui.
export const CONFIG_PATH = 'config/locutores.enc';
const CONFIG_CACHE_SECONDS = 60;

function configKey() {
  const secret = process.env.ADMIN_SECRET;
  if (!secret) throw new Error('ADMIN_SECRET não configurado');
  return keyFor(secret, 'config');
}

/** @returns {Promise<{config: object, etag: string | null}>} etag null = ainda não salvo */
export async function readConfig() {
  const res = await get(CONFIG_PATH, { access: 'public', useCache: false });
  if (!res) return { config: configFromCodeMap(parseCodeMap(process.env.CODIGOS_LOCUTORES)), etag: null };
  const text = await new Response(res.stream).text();
  return { config: decryptJson(text, configKey()), etag: res.blob.etag };
}

/** Grava só se ninguém mudou desde a leitura (etag); a primeira gravação não sobrescreve. */
export async function writeConfig(config, etag) {
  const guard = etag ? { ifMatch: etag } : { allowOverwrite: false };
  const result = await put(CONFIG_PATH, encryptJson(config, configKey()), {
    access: 'public',
    addRandomSuffix: false,
    contentType: 'application/octet-stream',
    cacheControlMaxAge: CONFIG_CACHE_SECONDS,
    ...guard,
  });
  return result.etag;
}

/** Painel: na primeira vez, salva o cadastro da variável pra os ids ficarem fixos. */
export async function readConfigForAdmin() {
  const current = await readConfig();
  if (current.etag) return current;
  const etag = await writeConfig(current.config, null);
  return { config: current.config, etag };
}

export async function loadLocutorMap() {
  const { config } = await readConfig();
  return codeMapFromConfig(config);
}
