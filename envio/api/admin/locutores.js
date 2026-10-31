// Painel: lista, cadastra, edita, troca código e remove locutores.
import { adminRoute } from '../_auth.js';
import { readConfigForAdmin, writeConfig } from '../_store.js';
import {
  validateLocutorInput, addLocutor, updateLocutor, replaceCode, removeLocutor, generateCode,
} from '../_admin.js';
import { json } from '../_locutores.js';

const byPrograma = (a, b) => a.programa.localeCompare(b.programa, 'pt-BR');
const allCodes = (config) => config.locutores.map((l) => l.codigo);

const listResponse = (config, extra = {}) =>
  json(200, { locutores: [...config.locutores].sort(byPrograma), ...extra });

async function save(next, etag, extra) {
  await writeConfig(next, etag);
  return listResponse(next, extra);
}

export const GET = adminRoute(async () => {
  const { config } = await readConfigForAdmin();
  return listResponse(config);
});

export const POST = adminRoute(async (request) => {
  const body = await request.json().catch(() => null);
  const { config, etag } = await readConfigForAdmin();

  if (body?.acao === 'novo-codigo') {
    const atual = config.locutores.find((l) => l.id === body.id);
    if (!atual) return json(404, { error: 'Locutor não encontrado.' });
    const codigo = generateCode(atual.programa, allCodes(config));
    return save(replaceCode(config, body.id, codigo), etag, { codigo });
  }

  const result = validateLocutorInput(body);
  if (!result.ok) return json(400, { error: result.error });
  const codigo = generateCode(result.value.programa, allCodes(config));
  return save(addLocutor(config, result.value, codigo), etag, { codigo });
});

export const PUT = adminRoute(async (request) => {
  const body = await request.json().catch(() => null);
  const result = validateLocutorInput(body);
  if (!result.ok) return json(400, { error: result.error });
  const { config, etag } = await readConfigForAdmin();
  const next = updateLocutor(config, body?.id, result.value);
  if (!next) return json(404, { error: 'Locutor não encontrado.' });
  return save(next, etag);
});

export const DELETE = adminRoute(async (request) => {
  const body = await request.json().catch(() => null);
  const { config, etag } = await readConfigForAdmin();
  const next = removeLocutor(config, body?.id);
  if (!next) return json(404, { error: 'Locutor não encontrado.' });
  return save(next, etag);
});
