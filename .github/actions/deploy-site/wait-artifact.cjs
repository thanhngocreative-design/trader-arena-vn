const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function waitForArtifact({id, name, list, pause = delay, attempts = 6}) {
  if (!Number.isSafeInteger(id) || id <= 0 || !name) throw Error('Missing uploaded artifact identity');
  for (let attempt = 0; attempt < attempts; attempt++) {
    const result = await list();
    if (!Array.isArray(result.artifacts)) throw Error('Invalid artifact metadata response');
    const found = result.artifacts.find(a => a.id === id && a.name === name && !a.expired && a.size_in_bytes > 0);
    if (found) return found;
    if (attempt + 1 < attempts) await pause(Math.min(15000, (attempt + 1) * 5000));
  }
  throw Error(`Uploaded artifact ${id} (${name}) is not visible; refusing to publish a different artifact`);
}

async function main() {
  const repo = process.env.GITHUB_REPOSITORY, run = process.env.GITHUB_RUN_ID;
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo || '') || !/^\d+$/.test(run || '')) throw Error('Invalid workflow context');
  const artifact = await waitForArtifact({
    id: Number(process.env.EXPECTED_ARTIFACT_ID), name: process.env.EXPECTED_ARTIFACT_NAME,
    list: async () => {
      const response = await fetch(`https://api.github.com/repos/${repo}/actions/runs/${run}/artifacts?per_page=100`, {
        headers: {Authorization: `Bearer ${process.env.GH_TOKEN}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2026-03-10'},
        redirect: 'manual', signal: AbortSignal.timeout(20000)
      });
      if (!response.ok) throw Error(`Artifact metadata HTTP ${response.status}`);
      return response.json();
    }
  });
  console.log(`Verified uploaded artifact ${artifact.id} (${artifact.name})`);
}
module.exports = {waitForArtifact};
if (require.main === module) main().catch(error => { console.error(error.message); process.exitCode = 1; });
