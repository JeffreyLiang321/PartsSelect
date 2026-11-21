// Vercel Cron target (see vercel.json). Free Hugging Face CPU Spaces sleep
// after 48h without traffic; a daily request keeps the backend awake so the
// first visitor doesn't wait for a cold start.
const SPACE_HEALTH_URL = 'https://jeffjeff20120112-partselect-agent.hf.space/api/health';

module.exports = async (req, res) => {
  try {
    const r = await fetch(SPACE_HEALTH_URL, { signal: AbortSignal.timeout(25000) });
    res.status(200).json({ space_status: r.status });
  } catch (err) {
    res.status(200).json({ space_status: 'unreachable' });
  }
};
