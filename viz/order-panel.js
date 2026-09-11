/* Source-owned order popup for the prebuilt website. Metric units throughout.
   The exported pure functions are shared with the viewer and Node regression tests. */
(function () {
  'use strict';
  const datasets = typeof module !== 'undefined' && module.exports
    ? require('./result-dataset.js') : window.PalletResultDataset;
  const finite = v => typeof v === 'number' && Number.isFinite(v);
  const positive = v => finite(v) && v > 0;
  const nonnegative = v => finite(v) && v >= 0;
  const sum = values => values.every(nonnegative) ? values.reduce((a, b) => a + b, 0) : null;
  function orderSummary(items, catalog) {
    if (!Array.isArray(items)) throw new Error('Order items are unavailable.');
    const bySku = new Map(catalog.map(s => [s.sku_id, s]));
    const rows = items.map(it => {
      if (!Number.isInteger(it.quantity) || it.quantity < 0) throw new Error('Invalid item quantity.');
      const sku = bySku.get(it.sku_id) || {};
      const dims = [sku.length, sku.width, sku.height];
      const volume = dims.every(positive) ? dims.reduce((a, b) => a * b, 1) : null;
      return {sku: it.sku_id, name: sku.name || '', quantity: it.quantity, dims,
        weight: nonnegative(sku.weight) ? sku.weight : null,
        lineWeight: nonnegative(sku.weight) ? sku.weight * it.quantity : null,
        lineVolume: volume === null ? null : volume * it.quantity};
    });
    return {rows, items: sum(rows.map(r => r.quantity)), skus: new Set(rows.map(r => r.sku)).size,
      weight: sum(rows.map(r => r.lineWeight)), volume: sum(rows.map(r => r.lineVolume)),
      missing: rows.filter(r => r.lineWeight === null || r.lineVolume === null).length};
  }
  function packStats(pack, order) {
    const boxes = pack && Array.isArray(pack.boxes) ? pack.boxes : null;
    if (!boxes) throw new Error('Packing artifact has no box list.');
    const warnings = [], expected = new Map(), counts = new Map(), ids = new Set();
    order.rows.forEach(r => expected.set(r.sku, (expected.get(r.sku) || 0) + r.quantity));
    let identityKnown = true, identityValid = true, geometryValid = true, top = 0;
    const volumes = [], weights = [];
    for (const b of boxes) {
      if (!b.sku_id) identityKnown = false;
      else counts.set(b.sku_id, (counts.get(b.sku_id) || 0) + 1);
      if (b.id !== undefined && b.id !== null) {
        if (ids.has(String(b.id))) identityValid = false;
        ids.add(String(b.id));
      }
      const d = b.dimensions || {}, p = b.position || {};
      const dims = [d.width, d.depth, d.height];
      const valid = dims.every(positive) && [p.x, p.y, p.z].every(finite);
      geometryValid = geometryValid && valid;
      if (valid) top = Math.max(top, p.z + d.height / 2);
      volumes.push(dims.every(positive) ? d.width * d.depth * d.height : null);
      weights.push(nonnegative(b.weight) ? b.weight : null);
    }
    counts.forEach((n, sku) => { if (!expected.has(sku) || n > expected.get(sku)) identityValid = false; });
    if (!identityValid) warnings.push('Duplicate box IDs or SKU quantities do not match this order.');
    if (!identityKnown) warnings.push('Some box SKU IDs are missing; only the box count can be compared.');
    if (!geometryValid) warnings.push('Invalid or missing box geometry; height and efficiency are unavailable.');
    const saved = pack.stats || {};
    if (finite(saved.placed) && saved.placed !== boxes.length)
      warnings.push('Saved placed count disagrees with the artifact. Counts below use the actual box list.');
    if (finite(saved.total) && saved.total !== order.items)
      warnings.push('Saved order total differs from the current order. Counts below use the current order.');
    const volume = sum(volumes), weight = sum(weights), c = pack.container || {};
    if (positive(c.height) && top > c.height + 1e-6) warnings.push('The stack exceeds the reported container height.');
    const lve = geometryValid && positive(c.width) && positive(c.depth) && positive(top) && positive(volume)
      ? c.width * c.depth * top / volume : null;
    const complete = order.items > 0 && boxes.length === order.items && identityValid;
    return {placed: boxes.length, remaining: identityValid && identityKnown ? Math.max(0, order.items - boxes.length) : null, volume, weight,
      top: geometryValid ? top : null, lve, complete, identityKnown, identityValid, warnings, container: c};
  }
  const METHODS = [
    {key:'packed', label:'Phase 1 + 2', endpoint:'result', description:'Full and partial layers forming the foundation. This is a prefix, not a completed hybrid pack.'},
    {key:'ep', label:'EP Hybrid', endpoint:'ep-result', description:'Phase 1 + 2 foundation, completed by the extreme-point heuristic.'},
    {key:'neat', label:'NEAT Hybrid', endpoint:'neat-result', description:'Phase 1 + 2 foundation, followed by the NEAT placement method.'},
    {key:'rl', label:'RL Full', endpoint:'rl-result', description:'PPO packing from the full order; no deterministic foundation is implied.'},
    {key:'rr', label:'RL + ReRanker', endpoint:'rr-result', description:'RL with learned candidate re-ranking. Candidate selection differs; this does not imply a newly trained PPO policy.'},
    {key:'remainder', label:'Layer remainder', description:'Unplaced items after Phase 1 + 2, arranged schematically. This is not a valid placement plan.'},
    {key:'schematic', label:'SKU schematic', description:'All order items arranged by SKU for inspection. No packing, efficiency or stability claim.'}
  ];
  function revisionsNewestFirst(revisions) {
    if (!Array.isArray(revisions) || !revisions.length) throw new Error('No result revisions available.');
    const stamp = r => Number.isFinite(Date.parse(r.date)) ? Date.parse(r.date) : -Infinity;
    return [...revisions].sort((a,b) => stamp(b)-stamp(a));
  }
  function revisionDataset(revision) {
    const qs = new URLSearchParams();
    if (revision.dataset) qs.set('dataset', revision.dataset);
    const config = datasets.fromSearch(qs.toString());
    if (!config.valid) throw new Error('Unknown result revision.');
    return config;
  }
  function revisionMethods(revision) {
    if (!revisionDataset(revision).experimental) return METHODS;
    if (revisionDataset(revision).epOnly) return METHODS.filter(m=>['ep','schematic'].includes(m.key)).map(m=>m.key==='ep'
      ? {...m,label:'EP clusters · 240 s',description:'Interleaved Phase 2 clusters and individual EP placements. This run does not contain PPO teacher demonstrations.'} : m);
    const descriptions = {
      packed:'Certified P1+2 teacher placements from this audit. This is not the EP run\'s foundation.',
      ep:'Full EP result from the selected research run. It is not a leaderboard replacement.',
      remainder:'Items remaining after this P1+2 teacher audit, arranged schematically. Not an EP remainder or a placement plan.'
    };
    const labels = {packed:'P1+2 teacher audit', ep:'EP experiment', remainder:'Teacher remainder'};
    return METHODS.map(m => ({...m, label:labels[m.key] || m.label, description:descriptions[m.key] || m.description}));
  }
  function viewerUrl(revision, orderId, method) {
    revisionDataset(revision); // Fail closed rather than mixing unknown revisions.
    const qs = new URLSearchParams({embed:'1', order:orderId, view:method});
    if (revision.dataset) qs.set('dataset', revision.dataset);
    return '/viz?' + qs.toString();
  }
  const model = {orderSummary, packStats, METHODS, revisionsNewestFirst, revisionDataset, revisionMethods, viewerUrl};
  if (typeof module !== 'undefined' && module.exports) module.exports = model;
  if (typeof window === 'undefined') return;
  window.PalletOrderModel = model;

  const states = new WeakMap();
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  function fmt(n, digits = 2, unit = '') {
    return finite(n) ? n.toLocaleString(undefined, {maximumFractionDigits:digits}) + unit : 'Not available';
  }
  function date(iso) {
    const d = iso ? new Date(iso) : null;
    return d && Number.isFinite(d.valueOf()) ? d.toLocaleString(undefined,
      {year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}) : 'Not recorded';
  }
  function pairs(target, cells) {
    for (const [label, value] of cells) target.append(el('dt', '', label), el('dd', '', value));
  }
  async function json(url, signal) {
    const response = await fetch(url, {signal});
    if (!response.ok) throw new Error('Could not load ' + url);
    return response.json();
  }
  function attach(modal, orderId) {
    const prior = states.get(modal);
    if (prior && prior.orderId === orderId && prior.root.isConnected) return;
    if (prior) { prior.controller.abort(); prior.root.remove(); }
    const body = modal.querySelector('.modal-body');
    if (!body) return;
    modal.dataset.orderPanel = orderId;
    const title = modal.querySelector('.modal-title');
    modal.setAttribute('role', 'dialog'); modal.setAttribute('aria-modal', 'true');
    if (title) { title.id = 'order-title-' + orderId; modal.setAttribute('aria-labelledby', title.id); }
    const root = el('section','op-panel'), controller = new AbortController();
    const state = {orderId, root, controller, selected:'packed', loaded:false, loadVersion:0};
    states.set(modal, state); body.prepend(root);
    root.append(el('p','op-muted','Loading order totals and packing strategies…'));
    const signal = controller.signal;
    signal.addEventListener('abort', () => state.revisionController?.abort(), {once:true});
    return json('/viz-api/result-revisions/' + encodeURIComponent(orderId), signal)
      .then(data => {
        if (signal.aborted || !root.isConnected) return;
        if(data.order_id !== orderId) throw new Error('Order revision mismatch');
        state.revisions = revisionsNewestFirst(data.revisions);
        body.scrollTop = 0;
        return loadRevision(state, state.revisions[0].id);
      }).catch(e => {
        if (signal.aborted || !root.isConnected) return;
        root.replaceChildren(el('p','op-error','Order data could not be verified. Please retry; no zero totals have been substituted.'));
        const retry = el('button','op-retry','Retry'); retry.type = 'button';
        retry.onclick = () => { states.delete(modal); root.remove(); attach(modal, orderId); };
        root.append(retry);
      });
  }
  function revisionControls(state) {
    const bar = el('div','op-result-date'), group = el('div');
    const id = 'op-result-date-' + state.orderId;
    const label = el('label','','Result date'); label.htmlFor = id;
    const select = el('select'); select.id = id;
    state.revisions.forEach((revision,i) => {
      let text = revision.label;
      if(revision.date_kind === 'last_published' && revision.date)
        text += ' · updated ' + new Date(revision.date).toLocaleDateString(undefined,{year:'numeric',month:'short',day:'numeric'});
      if(i===0) text += ' · latest';
      const option = el('option','',text); option.value = revision.id;
      select.append(option);
    });
    select.value = state.revision.id;
    select.onchange = () => loadRevision(state, select.value);
    group.append(label,select);
    bar.append(group,el('span','op-muted','Newest first · this order only'));
    state.root.append(bar);
    if(state.revision.note) state.root.append(el('p','op-run-note',state.revision.note));
  }
  async function loadRevision(state, revisionId) {
    const revision = state.revisions.find(r => r.id === revisionId);
    if(!revision) return;
    state.revisionController?.abort();
    const request = new AbortController(), version = ++state.loadVersion;
    state.revisionController = request; state.revision = revision; state.loaded = false;
    const signal = request.signal, {root,orderId} = state;
    root.replaceChildren(); revisionControls(state);
    root.setAttribute('aria-busy','true');
    root.append(el('p','op-muted','Loading the selected result date…'));
    // Discard the old frame immediately: a new date must never label old geometry.
    state.frame = null; state.message = null;
    try {
      const config = revisionDataset(revision);
      const sources = Promise.all(METHODS.filter(m => m.endpoint).map(async m => {
        const url = config.resultUrl(m.key, orderId);
        if(!url) return [m.key,{available:false,notInRevision:true}];
        try { return [m.key,await json(url,signal)]; }
        catch(e) { if(signal.aborted) throw e; return [m.key,{error:true}]; }
      }));
      const [order,catalog,entries] = await Promise.all([
        json(config.api+'/orders/'+encodeURIComponent(orderId),signal), json(config.api+'/skus',signal), sources]);
      if(signal.aborted || state.controller.signal.aborted || !root.isConnected || version!==state.loadVersion) return;
      if(order.order_id !== orderId) throw new Error('Order data mismatch');
      state.order = orderSummary(order.items,catalog); state.sources = Object.fromEntries(entries);
      state.loaded = true; root.setAttribute('aria-busy','false'); render(state);
    } catch(e) {
      if(signal.aborted || state.controller.signal.aborted || !root.isConnected || version!==state.loadVersion) return;
      root.replaceChildren(); revisionControls(state); root.setAttribute('aria-busy','false');
      root.append(el('p','op-error','This result date could not load. No older pack has been substituted.'));
      const retry = el('button','op-retry','Retry this date'); retry.type='button';
      retry.onclick=()=>loadRevision(state,revisionId); root.append(retry);
    }
  }
  function artifact(state, key) {
    const data = state.sources[key === 'remainder' ? 'packed' : key];
    return key === 'schematic' ? {available:true} : data || {available:false};
  }
  function packFor(data, key) { return key === 'packed' ? data.placed : key === 'remainder' ? data.remainder : data.pack; }
  function render(state) {
    const {root, order} = state;
    root.replaceChildren();
    revisionControls(state);
    const methods = revisionMethods(state.revision);
    const heading = el('div','op-heading');
    heading.append(el('h2','','Whole order'), el('span','op-muted',
      (state.revision.dataset ? 'Order snapshot for this run · ' : '')+'metres · kilograms'));
    const totals = el('dl','op-totals');
    [[order.items,'Items',0,''],[order.skus,'Unique SKUs',0,''],[order.weight,'Total weight',2,' kg'],[order.volume,'Item volume',4,' m³']]
      .forEach(([value,label,precision,unit]) => { const card=el('div','op-total'); pairs(card,[[label,fmt(value,precision,unit)]]); totals.append(card); });
    root.append(heading, totals);
    if (order.missing) root.append(el('p','op-notice',order.missing + ' order lines have incomplete SKU data. Affected totals are unavailable.'));
    const strategyHeading = el('div','op-heading');
    strategyHeading.append(el('h2','','Packing strategy'),el('span','op-muted','Compare the same order'));
    const strategies = el('div','op-strategies'); strategies.setAttribute('aria-label','Packing strategies');
    const workspace = el('div','op-workspace'), stage = el('div','op-stage'), frame = el('iframe');
    frame.title = '3D pallet for ' + state.orderId; frame.setAttribute('scrolling','no');
    const message = el('p','op-stage-message','Loading selected view…'); message.setAttribute('role','status');
    stage.append(frame,message); const details = el('section','op-details'); details.setAttribute('aria-live','polite');
    workspace.append(stage,details); root.append(strategyHeading,strategies,workspace);
    state.frame = frame; state.message = message;
    const ready = methods.filter(m => artifact(state,m.key).available);
    const preferred = ready.find(m => m.key === state.selected) || ready[0];
    function select(method) {
      state.selected = method.key;
      strategies.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.key === method.key)));
      renderDetails(details,state,method);
      const url = viewerUrl(state.revision,state.orderId,method.key);
      if (!frame.getAttribute('src')) frame.src = url;
      else frame.contentWindow.postMessage({type:'pallet-select-view',orderId:state.orderId,view:method.key},location.origin);
      message.hidden = false;
    }
    state.select = select;
    methods.forEach(method => {
      const data = artifact(state,method.key), button = el('button','op-strategy');
      button.type='button'; button.dataset.key=method.key; button.disabled=!data.available;
      button.setAttribute('aria-pressed','false');
      let status = data.error ? 'Load failed' : data.notInRevision ? 'Not in this run' : 'Not generated', kind = data.error ? 'error' : 'unavailable', count = 'No artifact';
      if (data.available) {
        if (method.key === 'schematic' || method.key === 'remainder') {
          kind='schematic'; status='Illustration only';
          count=fmt(method.key === 'schematic' ? order.items : (data.remainder?.boxes?.length),0)+' items';
        } else {
          try {
            const s=packStats(packFor(data,method.key),order);
            status=s.complete ? (s.identityKnown ? 'All items placed' : 'Count complete') : 'Partial pack';
            kind=s.complete ? 'complete' : 'partial'; count=fmt(s.placed,0)+' / '+fmt(order.items,0)+' placed';
            if (!s.identityValid || s.placed > order.items) { status='Check artifact'; kind='warning'; }
          } catch (_) { status='Invalid artifact'; kind='error'; button.disabled=true; }
        }
      }
      const badge=el('span','op-status',status); badge.dataset.state=kind;
      button.append(el('strong','',method.label),el('span','op-muted',count),badge);
      button.onclick=()=>select(method); strategies.append(button);
    });
    const first = preferred && strategies.querySelector('[data-key="'+preferred.key+'"]');
    if (first && !first.disabled) select(preferred); else select(methods.find(m=>m.key==='schematic'));
    frame.addEventListener('load',()=>frame.contentWindow.postMessage(
      {type:'pallet-select-view',orderId:state.orderId,view:state.selected},location.origin));
    renderItems(root, order);
  }
  function renderDetails(target,state,method) {
    target.replaceChildren(el('h2','',method.label),el('p','op-description',method.description));
    const data=artifact(state,method.key), pack=packFor(data,method.key), cells=[];
    if (pack && !['remainder','schematic'].includes(method.key)) {
      const s=packStats(pack,state.order);
      cells.push(['Placed',fmt(s.placed,0)+' / '+fmt(state.order.items,0)],['Remaining',fmt(s.remaining,0)],
        ['Stack height',fmt(s.top,3,' m')],['Placed item volume',fmt(s.volume,4,' m³')],
        ['Placed weight',fmt(s.weight,2,' kg')],['LVE · lower is tighter',fmt(s.lve,3)]);
      const metrics=el('dl','op-metrics'); pairs(metrics,cells); target.append(metrics);
      const c=s.container;
      target.append(el('p','op-muted','Container: '+[c.width,c.depth,c.height].map(v=>fmt(v,3)).join(' × ')+' m'));
      target.append(el('p','op-footer','LVE = pallet footprint × stack height ÷ placed item volume. Partial packs are not directly comparable to complete packs.'));
      s.warnings.forEach(w=>target.append(el('p','op-notice',w)));
      target.append(el('p','op-footer','Counts and geometry are read from this artifact. They do not certify stability or crush strength.'));
    }
    if(method.key==='schematic'){
      target.append(el('p','op-muted','No generated packing artifact. This illustration uses the order data for the selected result date.'));
      return;
    }
    const revision=el('section','op-revision'); revision.append(el('h3','',method.key==='remainder'?(state.revision.dataset?'Teacher revision':'Foundation revision'):'Artifact revision'));
    const pv=data.provenance, info=el('dl');
    if(pv?.run_completed_at) pairs(info,[['Run started',date(pv.run_started_at)],['Run finished',date(pv.run_completed_at)]]);
    else pairs(info,[['Added',date(pv?.added)],['Updated',date(pv?.updated)]]);
    if (pv?.commit && /^[a-f0-9]{7,40}$/i.test(pv.commit)) {
      const dd=el('dd'), link=el('a','',pv.commit.slice(0,12));
      link.href='https://github.com/Ritvik22/palletizing-benchmark/commit/'+pv.commit;
      link.target='_blank'; link.rel='noopener noreferrer'; dd.append(link); info.append(el('dt','','Commit'),dd);
    } else if(!pv?.code_commit) pairs(info,[['Commit','Not recorded']]);
    if(pv?.code_commit && /^[a-f0-9]{7,40}$/i.test(pv.code_commit)) {
      const dd=el('dd'), sha=String(pv.code_commit);
      if(/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+$/.test(pv.code_repository || '')) {
        const link=el('a','',sha.slice(0,12)); link.href=pv.code_repository+'/commit/'+sha;
        link.target='_blank'; link.rel='noopener noreferrer'; dd.append(link);
      } else dd.textContent=sha;
      info.append(el('dt','','Suite code'),dd);
    }
    const source=method.key==='remainder'?'packed':method.key;
    const prefix={packed:'results/',ep:'results_ep/',neat:'results_neat/',rl:'results_rl/',rr:'results_rl_reranker/'}[source];
    if(pv?.source_file) pairs(info,[['File',pv.source_file],['Order record',pv.source_record || state.orderId]]);
    else if(prefix) pairs(info,[['File',prefix+state.orderId+(source==='packed'?(method.key==='remainder'?'.remainder.json':'.placed.json'):'.packformation.json')]]);
    revision.append(info);
    if (pv?.subject) { const disclosure=el('details'); disclosure.append(el('summary','','Revision notes'),el('p','',pv.subject)); revision.append(disclosure); }
    const meta=pack?.metadata || pack?.meta || {};
    pairs(info,[['Model',meta.checkpoint || meta.model_version || pack?.checkpoint || 'Not recorded'],
      ['Algorithm',meta.code_revision || meta.git_commit || pv?.code_commit || 'Not recorded']]);
    revision.append(el('p','op-footer',pv?.run_completed_at
      ? 'Run dates describe the archived experiment; suite code identifies its source revision. This is not a model training date.'
      : 'Dates and commit identify publication of this pack, not its training run. Missing model/code revisions are shown explicitly.'));
    target.append(revision);
  }
  function renderItems(root,order) {
    const labels=['SKU / item','Qty','L × W × H (m)','Unit wt (kg)','Line wt (kg)','Line vol (m³)'];
    const table=el('table','op-items'); table.append(el('caption','','Order items'));
    const head=el('thead'), header=el('tr'); labels.forEach(t=>{const th=el('th','',t);th.scope='col';header.append(th);});head.append(header);
    const body=el('tbody');
    order.rows.forEach(r=>{
      const row=el('tr');
      const values=[r.sku,fmt(r.quantity,0),r.dims.every(positive)?r.dims.map(d=>fmt(d,3)).join(' × '):'Not available',fmt(r.weight,2),fmt(r.lineWeight,2),fmt(r.lineVolume,4)];
      values.forEach((v,i)=>{const cell=el('td','',v);cell.dataset.label=labels[i];if(i===0) cell.append(el('span','op-name',r.name));row.append(cell);}); body.append(row);
    });
    const foot=el('tfoot'), total=el('tr');
    ['Total',fmt(order.items,0),'','',fmt(order.weight,2),fmt(order.volume,4)].forEach(v=>total.append(el('td','',v)));
    foot.append(total);table.append(head,body,foot);root.append(table,el('p','op-footer','Line totals include quantity. Whole-order volume is the sum of item volumes, not the pallet bounding volume.'));
  }
  window.addEventListener('message',event=>{
    if(event.origin!==location.origin || event.data?.type!=='pallet-view-ready') return;
    document.querySelectorAll('.modal[data-order-panel]').forEach(modal=>{
      const s=states.get(modal);
      if(s?.frame?.contentWindow===event.source && s.orderId===event.data.orderId && s.selected===event.data.view){
        s.message.hidden=!event.data.error;
        if(event.data.error) s.message.textContent='The selected 3D view could not load. Its order statistics are still available.';
      }
    });
  });
  window.PalletOrderPanel = {attach};
})();
