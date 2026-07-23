async function logDownload(version, userAgent) {
  if (!process.env.SUPABASE_URL || !process.env.SUPABASE_ANON_KEY) return;
  try {
    await fetch(`${process.env.SUPABASE_URL}/rest/v1/app_downloads`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        apikey: process.env.SUPABASE_ANON_KEY,
        Authorization: `Bearer ${process.env.SUPABASE_ANON_KEY}`,
        Prefer: 'return=minimal',
      },
      body: JSON.stringify({ version: version || null, user_agent: userAgent || null }),
    });
  } catch (err) {
    // Best-effort: contagem não pode impedir o download do app.
  }
}

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).end();
  }

  const version = typeof req.query.v === 'string' ? req.query.v : null;
  await logDownload(version, req.headers['user-agent']);

  res.writeHead(302, { Location: '/downloads/encontro-adoradores.apk' });
  res.end();
}
