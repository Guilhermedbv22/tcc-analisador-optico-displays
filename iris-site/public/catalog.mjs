const knownModels = [
  {
    key: 'lg-24gs60f-b', brand: 'LG', name: 'LG UltraGear 24GS60F-B',
    aliases: ['LG UltraGear 24GS60F-B', 'LG 24GS60F-B', 'UltraGear 24GS60F-B', '24GS60F-B',
      'LG UltraGear 24GS60F B', 'LG 24GS60FB', 'LG UltraGear 24GS60FB', '24GS60FB'],
  },
  {
    key: 'aoc-lm522', brand: 'AOC', name: 'AOC LM522',
    aliases: ['AOC LM522', 'LM522', 'AOC LM 522', 'AOC LM-522'],
  },
  {
    key: 'hq-15-6hq-led', brand: 'HQ', name: '15.6HQ-LED',
    aliases: ['15.6HQ-LED', '15,6HQ-LED', '15.6HQ LED', 'HQ 15.6HQ-LED', 'HQ LED 15,6'],
  },
];

export function normalizeModel(value) {
  return String(value ?? '').normalize('NFKC').toLocaleLowerCase('pt-BR')
    .replace(/[‐‑‒–—−]/g, '-').replace(/\s*-\s*/g, '-').replace(/\s+/g, ' ').trim();
}

const aliases = new Map(knownModels.flatMap(model => model.aliases.map(alias => [normalizeModel(alias), model])));

export function modelIdentity(report) {
  const name = report.monitor.model.trim();
  const normalized = normalizeModel(name);
  const known = aliases.get(normalized);
  if (known) return known;
  return {key: 'modelo-' + normalized, name, brand: ''};
}

function datasetKey(report) {
  const c = report.conditions ?? {};
  if (c.report_parts > 1 && c.campaign_id && c.campaign_step && c.campaign_session && c.campaign_dataset) {
    return JSON.stringify([c.campaign_id, c.campaign_step, c.campaign_session, c.campaign_dataset,
      report.monitor.refresh_hz, normalizeModel(report.monitor.overdrive), report.simulation]);
  }
  return report.id;
}

function asSession(parts) {
  parts.sort((a,b) => (a.conditions?.report_part ?? 1) - (b.conditions?.report_part ?? 1));
  const lead = parts[0];
  const size = lead.conditions?.report_parts ?? 1;
  const complete = size === parts.length && parts.every((r,i) => (r.conditions?.report_part ?? 1) === i+1);
  return {lead, parts, size, complete, id:lead.id};
}

export function buildCatalog(reports) {
  const groups = new Map();
  for (const report of reports) {
    const model = modelIdentity(report);
    if (!groups.has(model.key)) groups.set(model.key, {...model, datasets: new Map()});
    const group = groups.get(model.key);
    const key = datasetKey(report);
    if (!group.datasets.has(key)) group.datasets.set(key, []);
    group.datasets.get(key).push(report);
  }
  return [...groups.values()].map(({datasets, ...model}) => ({
    ...model,
    sessions:[...datasets.values()].map(asSession)
      .sort((a,b) => String(b.lead.measured_at).localeCompare(String(a.lead.measured_at))),
  }));
}

export function matchesSession(session, filters) {
  const {lead} = session;
  const {query='', hz='', overdrive='', simulations=false} = filters;
  if (lead.simulation && !simulations) return false;
  if (hz && String(lead.monitor.refresh_hz) !== hz) return false;
  if (overdrive && normalizeModel(lead.monitor.overdrive) !== normalizeModel(overdrive)) return false;
  const text = normalizeModel([modelIdentity(lead).name, lead.monitor.model, lead.monitor.overdrive,
    lead.title, lead.operator, lead.conditions?.campaign_id].join(' '));
  const search = normalizeModel(query);
  return !search || text.includes(search) || aliases.get(search)?.key === modelIdentity(lead).key;
}

export function sessionHref(session) {
  return '?relatorio=' + encodeURIComponent(session.id) +
    (session.complete && session.size > 1 ? '&completo=1' : '');
}

// Each part has the number of valid GtG and peak readings as its weight.
export function sessionSummary(session) {
  const parts = session.parts.map(part => part.summary ?? {});
  const valid = parts.reduce((n,p) => n + (p.valid ?? 0),0);
  const total = parts.reduce((n,p) => n + (p.total ?? 0),0);
  const summary = {valid,total};
  for (const key of ['g2g_ms','overshoot_pct']) {
    const present = parts.filter(p => Number.isFinite(p[key]?.mean) && p.valid > 0);
    const weight = present.reduce((n,p) => n+p.valid,0);
    summary[key] = weight ? {
      mean:present.reduce((n,p) => n+p[key].mean*p.valid,0)/weight,
      min:Math.min(...present.map(p => p[key].min)),
      max:Math.max(...present.map(p => p[key].max)),
    } : null;
  }
  return summary;
}
