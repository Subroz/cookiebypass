export default async function handler(request, response) {
  if (request.method === "OPTIONS") {
    response.setHeader("Access-Control-Allow-Origin", "*");
    response.setHeader("Access-Control-Allow-Headers", "Content-Type");
    response.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
    response.status(204).end();
    return;
  }

  if (request.method !== "POST") {
    response.status(405).json({ error: "Use POST /api/test" });
    return;
  }

  const apiUrl = (process.env.MEDIA_API_URL || "").replace(/\/$/, "");
  const apiKey = process.env.MEDIA_API_KEY || "";
  if (!apiUrl || !apiKey) {
    response.status(500).json({
      error: "MEDIA_API_URL and MEDIA_API_KEY are required",
    });
    return;
  }

  try {
    const upstream = await fetch(`${apiUrl}/v1/metadata`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request.body || {}),
      signal: AbortSignal.timeout(8000),
    });
    const text = await upstream.text();
    response.setHeader("Access-Control-Allow-Origin", "*");
    response.setHeader("Content-Type", "application/json");
    response.status(upstream.status).send(text);
  } catch (error) {
    response.status(502).json({
      error: "upstream_failed",
      detail: error instanceof Error ? error.message : "Unknown upstream error",
    });
  }
}