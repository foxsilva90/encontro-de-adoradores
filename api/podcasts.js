const PLAYLIST_ID = 'PLdcKr-qi984jtu4vrA5MNc5YrXREE1lJD';
const MAX_RESULTS = 6;

// Cache na CDN da Vercel: 1 chamada à API do YouTube por hora, não por visitante.
// Protege a cota diária (10.000 unidades) mesmo sob tráfego alto.
const CACHE_CONTROL = 's-maxage=3600, stale-while-revalidate=86400';

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const apiKey = process.env.YOUTUBE_API_KEY;
  if (!apiKey) {
    return res.status(503).json({ error: 'Serviço indisponível' });
  }

  const url =
    'https://www.googleapis.com/youtube/v3/playlistItems' +
    '?part=snippet' +
    '&maxResults=' + MAX_RESULTS +
    '&playlistId=' + encodeURIComponent(PLAYLIST_ID) +
    '&key=' + encodeURIComponent(apiKey);

  try {
    const upstream = await fetch(url);
    if (!upstream.ok) {
      return res.status(502).json({ error: 'Falha ao carregar podcasts' });
    }

    const data = await upstream.json();

    // Devolve só o necessário — não repassa a resposta bruta do Google.
    const items = (data.items || [])
      .map((item) => {
        const s = item.snippet || {};
        const vid = s.resourceId && s.resourceId.videoId;
        if (!vid || !/^[a-zA-Z0-9_-]{11}$/.test(vid)) return null;
        if (s.title === 'Private video' || s.title === 'Deleted video') return null;

        const tn = s.thumbnails || {};
        const thumb = (tn.high || tn.medium || tn.default || {}).url || '';

        return { videoId: vid, title: s.title || '', thumbnail: thumb };
      })
      .filter(Boolean);

    res.setHeader('Cache-Control', CACHE_CONTROL);
    return res.status(200).json({ items });
  } catch (err) {
    return res.status(502).json({ error: 'Falha ao carregar podcasts' });
  }
}
