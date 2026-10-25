/**
 * Netlify Function: data.js (Node 18+)
 * Secure data proxy for private repository state files.
 */

const EXACT_ALLOWLIST = new Set([
  "scan_results.json",
  "trades.json",
  "open_positions.json",
  "backtest_results.json",
]);
const ARCHIVE_REGEX = /^archive\/[A-Za-z0-9_.-]+$/;

exports.handler = async (event) => {
  // Read ?file=
  const file = event.queryStringParameters?.file;

  // Reject missing, empty, or directory traversal paths
  if (!file || file.includes("..")) {
    return {
      statusCode: 404,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
      body: JSON.stringify({ error: "not found" }),
    };
  }

  // ALLOWLIST check: exactly {scan_results.json, trades.json, open_positions.json} or archive regex
  const isAllowed = EXACT_ALLOWLIST.has(file) || ARCHIVE_REGEX.test(file);
  if (!isAllowed) {
    return {
      statusCode: 404,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
      body: JSON.stringify({ error: "not found" }),
    };
  }

  // Header check: x-dash-key === process.env.DASH_KEY_HASH
  const headers = event.headers || {};
  const dashKey =
    headers["x-dash-key"] ||
    headers["X-Dash-Key"] ||
    headers["X-DASH-KEY"] ||
    headers["x-dash-key".toLowerCase()] ||
    "";

  const expectedKey = process.env.DASH_KEY_HASH;
  if (!expectedKey || dashKey !== expectedKey) {
    return {
      statusCode: 401,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
      body: JSON.stringify({ error: "unauthorized" }),
    };
  }

  // Fetch from raw GitHub with PAT authorization
  const owner = process.env.GH_OWNER || "toanilsharma";
  const repo = process.env.GH_REPO || "small-cap-swing-scanner";
  const upstreamUrl = `https://raw.githubusercontent.com/${owner}/${repo}/main/${file}`;

  try {
    const upstreamRes = await fetch(upstreamUrl, {
      headers: {
        Authorization: `Bearer ${process.env.GH_PAT || ""}`,
        "User-Agent": "SmallCapSwingDashboard/1.0",
      },
    });

    if (upstreamRes.status === 404) {
      return {
        statusCode: 404,
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
        },
        body: JSON.stringify({ error: "not found" }),
      };
    }

    if (!upstreamRes.ok) {
      return {
        statusCode: 502,
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
        },
        body: JSON.stringify({ error: "upstream fetch failed" }),
      };
    }

    const bodyText = await upstreamRes.text();
    return {
      statusCode: 200,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
      body: bodyText,
    };
  } catch (err) {
    // Never echo PAT
    return {
      statusCode: 502,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
      body: JSON.stringify({ error: "upstream fetch failed" }),
    };
  }
};
