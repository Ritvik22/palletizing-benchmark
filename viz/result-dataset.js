/* Explicit data selection: never silently mix an experiment with published packs. */
(function (root) {
  'use strict';
  const EXPERIMENT = 'baseline-library-20260910-2m';
  const CLUSTER_EXPERIMENT = 'ep-clusters-240s-20260911';
  function fromSearch(search) {
    const id = new URLSearchParams(search).get('dataset');
    const epOnly = id === CLUSTER_EXPERIMENT;
    const experimental = id === EXPERIMENT || epOnly;
    const valid = !id || experimental;
    const api = experimental ? '/viz-api/experiments/' + id : '/viz-api';
    return {valid, experimental, epOnly, api,
      labels: {packed: experimental ? 'P1+2 teacher audit' : 'Phase 1+2',
        remainder: experimental ? 'P1+2 teacher audit Remainder' : 'Phase 1+2 Remainder',
        ep: epOnly ? 'EP clusters · 240 s' : experimental ? 'EP Sep 10 experiment' : 'EP Hybrid', neat: 'NEAT Hybrid',
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
  const api = {EXPERIMENT, CLUSTER_EXPERIMENT, fromSearch};
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PalletResultDataset = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
