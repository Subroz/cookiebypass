async function handler(_request, response) {
  const apiUrl = (process.env.MEDIA_API_URL || "").replace(/\/$/, "");

  if (!apiUrl) {
    response.status(500).json({
      status: "error",
      error: "MEDIA_API_URL is not configured",
    });
    return;
  }

  try {
    const upstream = await fetch(`${apiUrl}/health/diagnostics`, {
      signal: AbortSignal.timeout(9000),
    });
    const body = await upstream.text();
    response.setHeader("Content-Type", "application/json");
    response.status(upstream.status).send(body);
  } catch (error) {
    response.status(502).json({
      status: "error",
      error: "VPS health check failed",
      detail: error instanceof Error ? error.message : "Unknown upstream error",
    });
  }
}

module.exports = handler;