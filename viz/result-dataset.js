/* Explicit data selection: never silently mix an experiment with published packs. */
(function (root) {
  'use strict';
  const EXPERIMENT = 'baseline-library-20260910-2m';
  const CLUSTER_EXPERIMENT = 'ep-clusters-240s-20260911';
  const ZIP1_EXPERIMENT = 'ep-zip1-10workers-20260914';
  const BEST_KNOWN_EXPERIMENT = 'ep-best-known-1000-20260918';
  const LATEST_EP_EXPERIMENT = 'ep-latest-multistart-1000-12workers-20260918';
  function fromSearch(search) {
    const id = new URLSearchParams(search).get('dataset');
    const bestKnown = id === BEST_KNOWN_EXPERIMENT;
    const latestEP = id === LATEST_EP_EXPERIMENT;
    const epOnly = id === CLUSTER_EXPERIMENT || id === ZIP1_EXPERIMENT || bestKnown || latestEP;
    const experimental = id === EXPERIMENT || epOnly;
    const valid = !id || experimental;
    const api = experimental ? '/viz-api/experiments/' + id : '/viz-api';
    return {valid, experimental, epOnly, bestKnown, latestEP, api,
      epDescription: latestEP ? 'Fresh common-schedule EP run: 953/1000 complete, with 155,607 of 155,904 boxes accepted. All 1,000 packs passed the independent rigid-static audit. Not leaderboard data or a PPO teacher.' : bestKnown ? 'Best-known audited EP packs selected across development runs: 998/1000 complete, 3 boxes remaining. Not a fresh common-schedule benchmark or PPO teacher.' : 'Interleaved Phase 2 clusters and individual EP placements. This run does not contain PPO teacher demonstrations.',
      labels: {packed: experimental ? 'P1+2 teacher audit' : 'Phase 1+2',
        remainder: experimental ? 'P1+2 teacher audit Remainder' : 'Phase 1+2 Remainder',
        ep: latestEP ? 'EP fresh run · Sep 18–19' : bestKnown ? 'EP best-known · Sep 18' : id === ZIP1_EXPERIMENT ? 'EP clusters · ZIP 1 · 240 s' : epOnly ? 'EP clusters · 240 s' : experimental ? 'EP Sep 10 experiment' : 'EP Hybrid', neat: 'NEAT Hybrid',
        rl: 'RL Full', rr: 'RL + ReRanker', epv4: 'EP Bounded',
        schematic: 'Schematic by SKU'},
      resultUrl(method, orderId) {
        if (!valid) throw new Error('Unknown result dataset');
        if (epOnly && method !== 'ep') return null;
        const endpoints = {packed:'result', ep:'ep-result', neat:'neat-result',
          rl:'rl-result', rr:'rr-result', epv4:'epv4-result'};
        if (!(method in endpoints) || (experimental && !['packed', 'ep'].includes(method))) return null;
        return api + '/' + endpoints[method] + '/' + encodeURIComponent(orderId);
      },
      switchUrl(orderId) {
        const qs = new URLSearchParams({view: experimental ? 'packed' : 'ep'});
        if (!experimental) qs.set('dataset', EXPERIMENT);
        if (orderId) qs.set('order', orderId);
        return '/viz?' + qs;
      }};
  }
  const api = {EXPERIMENT, CLUSTER_EXPERIMENT, ZIP1_EXPERIMENT, BEST_KNOWN_EXPERIMENT, LATEST_EP_EXPERIMENT, fromSearch};
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PalletResultDataset = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
