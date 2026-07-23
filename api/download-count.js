export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).end();
  }

  if (!process.env.SUPABASE_URL || !process.env.SUPABASE_ANON_KEY) {
    return res.status(503).json({ error: 'Serviço indisponível' });
  }

  try {
    const url = `${process.env.SUPABASE_URL}/rest/v1/app_downloads?select=id&limit=0`;
    const response = await fetch(url, {
      headers: {
        apikey: process.env.SUPABASE_ANON_KEY,
        Authorization: `Bearer ${process.env.SUPABASE_ANON_KEY}`,
        Prefer: 'count=exact',
      },
    });
    const contentRange = response.headers.get('content-range') || '';
    const total = Number(contentRange.split('/')[1]) || 0;
    return res.status(200).json({ downloads: total });
  } catch (err) {
    return res.status(502).json({ error: 'Falha ao consultar contagem' });
  }
}
