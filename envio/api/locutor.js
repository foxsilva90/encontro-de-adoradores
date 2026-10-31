// Confere o código do locutor e devolve o nome do programa dele.
import { parseCodeMap, findProgramByCode, json } from './_locutores.js';

export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  const programa = findProgramByCode(parseCodeMap(process.env.CODIGOS_LOCUTORES), body.codigo);
  if (!programa) return json(401, { error: 'Código não encontrado. Confira com a equipe da rádio.' });
  return json(200, { programa });
}
