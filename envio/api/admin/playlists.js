// Sugestões de playlist pro formulário. Com AZURACAST_* configurado, lista
// direto do AzuraCast; sem, usa as playlists que já estão no cadastro.
import { adminRoute } from '../_auth.js';
import { readConfigForAdmin } from '../_store.js';
import { json } from '../_locutores.js';

async function fromAzuraCast() {
  const { AZURACAST_BASE_URL: base, AZURACAST_API_KEY: key, AZURACAST_STATION: station } = process.env;
  if (!base || !key || !station) return null;
  const resp = await fetch(`${base.replace(/\/$/, '')}/api/station/${station}/playlists`, {
    headers: { 'X-API-Key': key },
  });
  if (!resp.ok) return null;
  const list = await resp.json();
  return Array.isArray(list) ? list.map((p) => p.name).filter(Boolean) : null;
}

export const GET = adminRoute(async () => {
  const live = await fromAzuraCast().catch(() => null);
  if (live) return json(200, { fonte: 'azuracast', playlists: [...new Set(live)].sort() });
  const { config } = await readConfigForAdmin();
  const known = config.locutores.flatMap((l) => l.destinos.flatMap((d) => d.playlists));
  return json(200, { fonte: 'cadastro', playlists: [...new Set(known)].sort() });
});
