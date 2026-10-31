// Confere o código do locutor e devolve o programa e as opções de destino.
import { findLocutorByCode, json } from './_locutores.js';
import { loadLocutorMap } from './_store.js';

export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  const locutor = findLocutorByCode(await loadLocutorMap(), body.codigo);
  if (!locutor) return json(401, { error: 'Código não encontrado. Confira com a equipe da rádio.' });
  return json(200, {
    programa: locutor.programa,
    // Só os nomes: as playlists não precisam ir pro navegador.
    destinos: locutor.destinos.length > 1 ? locutor.destinos.map((d) => d.nome) : [],
  });
}
