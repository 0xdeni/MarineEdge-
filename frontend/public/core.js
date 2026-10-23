/* =====================================================================================
   MarineEdge — core: config, geo helpers, sea-lane routing, mock AIS provider,
   voyage splitting and the red-flag rule engine. No DOM access in this file.
   ===================================================================================== */
'use strict';
const GEO = window.__GEO__;
const NOW = Date.now();
const H = 3600e3, D = 24 * H, YEAR = 365 * D;

/* ---- config/rules.yaml equivalent: every threshold the brief lists, in one place ---- */
const RULES = {
  portCall:      { maxSpeedKn: 0.5, minHours: 6, portRadiusNm: 5, mergeWithinHours: 36 },
  sanctions:     { lookbackMonths: 12, lists: ['OFAC SDN', 'EU', 'UK'] },
  aisGap:        { minHours: 6, highHours: 24, nearSensitiveNm: 100 },
  draughtChange: { minMeters: 1.0 },
  sts:           { maxDistM: 500, maxSpeedKn: 1.0, minHours: 2 },
  positionJump:  { maxImpliedKn: 30 },
  identity:      { mediumIfMoreThan: 1 },
};

/* ---------------------------------- helpers ---------------------------------- */
const RAD = Math.PI / 180;
const nmDist = (lat1, lon1, lat2, lon2) => {
  const dl = (lat2 - lat1) * RAD, dn = (lon2 - lon1) * RAD;
  const a = Math.sin(dl / 2) ** 2 + Math.cos(lat1 * RAD) * Math.cos(lat2 * RAD) * Math.sin(dn / 2) ** 2;
  return 6880.13 * Math.asin(Math.sqrt(a));
};
const bearing = (lat1, lon1, lat2, lon2) => {
  const y = Math.sin((lon2 - lon1) * RAD) * Math.cos(lat2 * RAD);
  const x = Math.cos(lat1 * RAD) * Math.sin(lat2 * RAD) - Math.sin(lat1 * RAD) * Math.cos(lat2 * RAD) * Math.cos((lon2 - lon1) * RAD);
  return (Math.atan2(y, x) / RAD + 360) % 360;
};
const destPoint = (lat, lon, brg, nm) => {
  const R = 3440.065, la = lat * RAD, lo = lon * RAD, b = brg * RAD, d = nm / R;
  const la2 = Math.asin(Math.sin(la) * Math.cos(d) + Math.cos(la) * Math.sin(d) * Math.cos(b));
  const lo2 = lo + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(la), Math.cos(d) - Math.sin(la) * Math.sin(la2));
  return [la2 / RAD, lo2 / RAD];
};
const pointInPoly = (lon, lat, poly) => {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > lat) !== (yj > lat) && lon < xi + (lat - yi) * (xj - xi) / (yj - yi)) inside = !inside;
  }
  return inside;
};
// distance (nm) from a point to a polygon outline; 0 when inside
const polyDistNm = (lon, lat, poly) => {
  if (pointInPoly(lon, lat, poly)) return 0;
  const k = Math.cos(lat * RAD) * 60, px = lon * k, py = lat * 60; let best = Infinity;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const ax = poly[j][0] * k, ay = poly[j][1] * 60, bx = poly[i][0] * k, by = poly[i][1] * 60;
    const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy;
    const t = L2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / L2)) : 0;
    best = Math.min(best, Math.hypot(px - (ax + t * dx), py - (ay + t * dy)));
  }
  return best;
};
const mulberry32 = seed => () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
const pad2 = n => String(n).padStart(2, '0');
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
let TIME_LOCAL = false; // settings: show times in UTC (default) or the device's local time
const TZ = () => TIME_LOCAL ? 'local' : 'UTC';
const dp = t => { const d = new Date(t); return TIME_LOCAL ? { d: d.getDate(), m: d.getMonth(), y: d.getFullYear(), hh: d.getHours(), mm: d.getMinutes() } : { d: d.getUTCDate(), m: d.getUTCMonth(), y: d.getUTCFullYear(), hh: d.getUTCHours(), mm: d.getUTCMinutes() }; };
const fmtDT = t => { const p = dp(t); return `${p.d} ${MON[p.m]} ${pad2(p.hh)}:${pad2(p.mm)}`; };
const fmtD = t => { const p = dp(t); return `${p.d} ${MON[p.m]}`; };
const fmtDY = t => { const p = dp(t); return `${p.d} ${MON[p.m]} ${p.y}`; };
const fmtMon = t => MON[dp(t).m];
const fmtRange = (a, b) => { const pa = dp(a), pb = dp(b); if (pa.m !== pb.m) return `${fmtD(a)} to ${fmtD(b)}`; return pa.d === pb.d ? fmtD(a) : `${pa.d}–${pb.d} ${MON[pa.m]}`; };
const fmtISO = t => TIME_LOCAL ? `${fmtDY(t)} ${pad2(dp(t).hh)}:${pad2(dp(t).mm)} local` : new Date(t).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
const fmtDur = ms => { const h = ms / H; if (h < 48) return `${Math.round(h)} h`; return `${(h / 24).toFixed(h / 24 < 10 ? 1 : 0)} d`; };
const fmtDM = (lat, lon) => {
  const f = (v, pos, neg, w) => { const a = Math.abs(v), d = Math.floor(a), m = ((a - d) * 60).toFixed(1); return `${String(d).padStart(w, '0')}°${m.padStart(4, '0')}′${v >= 0 ? pos : neg}`; };
  return `${f(lat, 'N', 'S', 2)} ${f(lon, 'E', 'W', 3)}`;
};
const fmtN = n => n.toLocaleString('en-GB');
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ----------------------------- regions & ports ----------------------------- */
const PORT = {}; // id -> port (with region key)
for (const key of ['A', 'B']) for (const p of GEO.regions[key].ports) { p.region = key; PORT[p.id] = p; }
const ZONE = Object.fromEntries(GEO.zones.map(z => [z.id, z]));
const zoneAt = (lon, lat) => GEO.zones.find(z => z.enabled !== false && pointInPoly(lon, lat, z.poly)) || null;
const nearestZone = (lon, lat) => { let best = null, bd = Infinity; for (const z of GEO.zones) { if (z.enabled === false) continue; const d = polyDistNm(lon, lat, z.poly); if (d < bd) { bd = d; best = z; } } return { zone: best, nm: bd }; };
const jammingAt = (lon, lat) => GEO.jamming.find(j => lon >= j.box[0] && lat >= j.box[1] && lon <= j.box[2] && lat <= j.box[3]) || null;
const nearestPort = (lon, lat, region) => { let best = null, bd = Infinity; for (const p of GEO.regions[region].ports) { const d = nmDist(lat, lon, p.b[1], p.b[0]); if (d < bd) { bd = d; best = p; } } return { port: best, nm: bd }; };

/* ------------------------------- sea-lane routing ------------------------------- */
const ROUTER = {};
for (const key of ['A', 'B']) {
  const R = GEO.regions[key], adj = R.nodes.map(() => []);
  for (const [a, b] of R.edges) { const w = nmDist(R.nodes[a][1], R.nodes[a][0], R.nodes[b][1], R.nodes[b][0]); adj[a].push([b, w]); adj[b].push([a, w]); }
  ROUTER[key] = { adj, cache: new Map() };
}
function seaRoute(region, fromNode, toNode) {
  const key = fromNode + '>' + toNode, rt = ROUTER[region];
  if (rt.cache.has(key)) return rt.cache.get(key);
  const nodes = GEO.regions[region].nodes, dist = new Map([[fromNode, 0]]), prev = new Map();
  const pq = [[0, fromNode]]; // tiny binary-heap-free Dijkstra (graph is small)
  while (pq.length) {
    let bi = 0; for (let i = 1; i < pq.length; i++) if (pq[i][0] < pq[bi][0]) bi = i;
    const [d, u] = pq.splice(bi, 1)[0];
    if (u === toNode) break;
    if (d > dist.get(u)) continue;
    for (const [v, w] of rt.adj[u]) { const nd = d + w; if (nd < (dist.get(v) ?? Infinity)) { dist.set(v, nd); prev.set(v, u); pq.push([nd, v]); } }
  }
  const path = [toNode]; while (path[path.length - 1] !== fromNode) { const p = prev.get(path[path.length - 1]); if (p === undefined) break; path.push(p); }
  path.reverse();
  const out = { pts: path.map(i => nodes[i]), nm: dist.get(toNode) ?? 0 };
  rt.cache.set(key, out); return out;
}

/* ------------------------------------ fleet ------------------------------------ */
const TRADES = {
  bs_grain: ['ODS', 'CHO', 'PIV', 'CND', 'VAR', 'BOJ', 'NVS', 'TAM', 'SAM', 'MER', 'ISK', 'ALY', 'DAM', 'PSD', 'BAT', 'POT'],
  bs_oil:   ['NVS', 'TUA', 'TAM', 'KAV', 'CND', 'BOJ', 'SPS', 'BAT', 'MER', 'CEY', 'ALY', 'AMB', 'IZT', 'LIM', 'HAI'],
  bs_box:   ['ODS', 'CND', 'VAR', 'NVS', 'AMB', 'GEM', 'MER', 'PSD', 'POT', 'PIR', 'HAI', 'LIM'],
  bs_gen:   ['SAM', 'TRA', 'BAT', 'POT', 'BND', 'ISK', 'MER', 'VAR', 'CND', 'ODS', 'KAV', 'TAM'],
  g_crude:  ['RTA', 'MAA', 'BOT', 'JUB', 'RUW', 'DAS', 'FJR', 'SOH'],
  g_prod:   ['RUW', 'FJR', 'JEA', 'SOH', 'MCT', 'SLL', 'DMM', 'BAH', 'MES', 'DUQ'],
  g_bulk:   ['JEA', 'SOH', 'DUQ', 'SLL', 'KHL', 'HMD', 'DMM', 'UMQ', 'KWI', 'JUB', 'GWD', 'MCT', 'BAH'],
  g_box:    ['JEA', 'KHF', 'SLL', 'KHL', 'HMD', 'SOH', 'DMM', 'UMQ', 'KWI', 'BAH', 'MCT', 'GWD', 'DXB', 'SHJ'],
  g_gas:    ['RLF', 'DAS', 'MES', 'RUW', 'SOH', 'FJR', 'JEA'],
};
const SENSITIVE_PORTS = { A: ['SEV', 'FEO', 'KER', 'BER', 'MAR', 'TAR', 'LAT'], B: ['BND2', 'BUZ', 'KHK', 'BIK', 'ASA', 'LEN', 'CHB', 'JSK'] };
const TYPE_LABEL = { tanker: 'Tanker', bulk: 'Bulk carrier', container: 'Container ship', gas: 'Gas carrier', other: 'General cargo' };
const MID = { 'Panama': ['351', '352', '353', '370', '371'], 'Liberia': ['636', '637'], 'Marshall Islands': ['538'], 'Malta': ['215', '229', '248', '256'], 'Türkiye': ['271'], 'Greece': ['237', '239', '240'], 'Cyprus': ['209', '210', '212'], 'Togo': ['671'], 'Cameroon': ['613'], 'Gabon': ['626'], 'Palau': ['511'], 'Comoros': ['616'], 'Sierra Leone': ['667'], 'UAE': ['470', '471'], 'Oman': ['461'], 'Iran': ['422'], 'Russia': ['273'], 'Georgia': ['213'], 'Qatar': ['466'], 'India': ['419'], 'Singapore': ['563', '564', '565'], 'Saudi Arabia': ['403'], 'Kuwait': ['447'], 'Bahamas': ['308', '309', '311'] };
const CALL = { 'Panama': '3F', 'Liberia': 'D5', 'Marshall Islands': 'V7', 'Malta': '9H', 'Türkiye': 'TC', 'Greece': 'SV', 'Cyprus': '5B', 'Togo': '5V', 'Cameroon': 'TJ', 'Gabon': 'TR', 'Palau': 'T8', 'Comoros': 'D6', 'Sierra Leone': '9L', 'UAE': 'A6', 'Oman': 'A4', 'Iran': 'EP', 'Russia': 'UB', 'Georgia': '4L', 'Qatar': 'A7', 'India': 'VT', 'Singapore': '9V', 'Saudi Arabia': 'HZ', 'Kuwait': '9K', 'Bahamas': 'C6' };
const IACS = ['DNV', 'Lloyd’s Register', 'ABS', 'Bureau Veritas', 'RINA', 'ClassNK', 'KR', 'CCS', 'IRS', 'Türk Loydu'];
const IG_PI = ['Gard', 'Skuld', 'NorthStandard', 'West P&I', 'Britannia', 'UK P&I Club', 'Steamship Mutual', 'American Club', 'The London P&I Club'];
const BUILDERS = { bulk: ['Oshima Shipbuilding (JP)', 'Tsuneishi Zhoushan (CN)', 'Imabari Shipbuilding (JP)', 'Jiangsu New Yangzi (CN)', 'Hyundai Mipo (KR)', 'COSCO Zhoushan (CN)'], tanker: ['Hyundai Mipo (KR)', 'Samsung HI (KR)', 'DSME (KR)', 'Sumitomo HI (JP)', 'New Times Shipbuilding (CN)', 'STX Offshore (KR)'], container: ['Hyundai HI (KR)', 'Samsung HI (KR)', 'Jiangsu New Yangzi (CN)', 'CSBC (TW)'], gas: ['Hudong-Zhonghua (CN)', 'Samsung HI (KR)', 'Hyundai HI (KR)', 'Kawasaki HI (JP)'], other: ['Volgograd Shipyard (RU)', 'Sefine Shipyard (TR)', 'Damen (NL)', 'Nevskiy Shipyard (RU)', 'Hanjin (KR)'] };
const CO = { A: [['Pontus Maritime Ltd', 'Limassol'], ['Dobrogea Shipping SA', 'Constanța'], ['Hazar Denizcilik AŞ', 'Istanbul'], ['Meridian Bulk Carriers SA', 'Piraeus'], ['Karadeniz Lines Ltd', 'Valletta'], ['Aegean Dawn Maritime Inc', 'Majuro'], ['Boreas Ship Management', 'Athens'], ['Thracian Navigation Co', 'Varna'], ['Colchis Shipping LLC', 'Batumi']], B: [['Gulf Crescent Shipping LLC', 'Dubai'], ['Al Batinah Marine SAOC', 'Sohar'], ['Oryx Tankers DMCC', 'Dubai'], ['Pearl Gulf Navigation', 'Doha'], ['Tigris Freight Lines', 'Basra'], ['Dhofar Maritime LLC', 'Salalah'], ['Fenix Ship Management', 'Singapore'], ['Arabian Horizon Shipping', 'Abu Dhabi'], ['Sindh Bulk Carriers', 'Mumbai']] };
const OPAQUE = [['Sunrise Maritime Inc', 'Majuro'], ['Golden Wave Shipping Ltd', 'Road Town'], ['Blue Lagoon Marine Corp', 'Majuro'], ['Starlight Vessels Ltd', 'Hong Kong'], ['Seabird Holdings SA', 'Panama City']];

// name, imo, flag, type, subtype, dwt, built, region, trade, risk, opts
const FLEET_DEF = [
  ['PONTIC HARVEST', 9000011, 'Marshall Islands', 'bulk', 'Panamax bulk carrier', 76400, 2011, 'A', 'bs_grain', 0.10],
  ['DOBRUJA STAR', 9000012, 'Malta', 'bulk', 'Supramax bulk carrier', 56800, 2009, 'A', 'bs_grain', 0.15],
  ['AZOV CRESCENT', 9000013, 'Panama', 'bulk', 'Handysize bulk carrier', 33500, 2004, 'A', 'bs_grain', 0.80, { ex: ['SILVER DUNE'], hist: [['name', 'SILVER DUNE', 'AZOV CRESCENT', 7], ['flag', 'Comoros', 'Panama', 7], ['mmsi', '616', null, 7]] }],
  ['KUBAN SPIRIT', 9000014, 'Gabon', 'tanker', 'Aframax crude tanker', 112800, 2006, 'A', 'bs_oil', 0.90, { sanctions: [['OFAC SDN', '2026-03-14', 'RUSSIA-EO14024'], ['EU', '2026-04-02', 'Reg. 833/2014, Annex XLII']], hist: [['flag', 'Panama', 'Gabon', 5], ['mmsi', '352', null, 5]], opaque: true }],
  ['MARMARA PEARL', 9000015, 'Türkiye', 'container', 'Feeder container ship · 1,700 TEU', 24100, 2015, 'A', 'bs_box', 0.05],
  ['ANATOLIAN GRAIN', 9000016, 'Türkiye', 'bulk', 'Handymax bulk carrier', 45300, 2012, 'A', 'bs_grain', 0.20],
  ['TAURUS VOYAGER', 9000017, 'Liberia', 'tanker', 'MR product tanker', 49900, 2017, 'A', 'bs_oil', 0.30],
  ['SARMATIA', 9000018, 'Greece', 'bulk', 'Panamax bulk carrier', 81200, 2019, 'A', 'bs_grain', 0.10],
  ['SILVER REACH', 9000019, 'Cameroon', 'other', 'General cargo ship', 8900, 2001, 'A', 'bs_gen', 0.95, { ex: ['ORION LEGEND'], sanctions: [['EU', '2025-12-16', 'Reg. 2022/263 (Crimea)'], ['UK', '2026-01-20', 'Russia (Sanctions) Regulations']], hist: [['name', 'ORION LEGEND', 'SILVER REACH', 9], ['flag', 'Togo', 'Cameroon', 4], ['mmsi', '671', null, 4]], opaque: true }],
  ['COLCHIS TRADER', 9000021, 'Georgia', 'bulk', 'Handysize bulk carrier', 37100, 2010, 'A', 'bs_grain', 0.25],
  ['BOSPORUS LINK', 9000022, 'Liberia', 'container', 'Container ship · 2,500 TEU', 35200, 2008, 'A', 'bs_box', 0.10],
  ['THRACIAN SUN', 9000023, 'Marshall Islands', 'tanker', 'Suezmax crude tanker', 157000, 2010, 'A', 'bs_oil', 0.55],
  ['KARADENIZ ARROW', 9000024, 'Panama', 'bulk', 'Ultramax bulk carrier', 63300, 2020, 'A', 'bs_grain', 0.10],
  ['MEOTIDA', 9000025, 'Russia', 'other', 'General cargo ship', 5200, 1998, 'A', 'bs_gen', 0.85],
  ['HALKIDIKI BREEZE', 9000026, 'Cyprus', 'bulk', 'Kamsarmax bulk carrier', 82000, 2016, 'A', 'bs_grain', 0.15],
  ['LEVANT STAR', 9000027, 'Cameroon', 'tanker', 'MR product tanker', 47000, 2004, 'A', 'bs_oil', 0.90, { ex: ['ATLAS KING'], sanctions: [['OFAC SDN', '2026-05-08', 'SYRIA']], hist: [['name', 'ATLAS KING', 'LEVANT STAR', 6], ['flag', 'Palau', 'Cameroon', 6], ['mmsi', '511', null, 6]], opaque: true }],
  ['BLUE HORIZON', 9000028, 'Malta', 'bulk', 'Handymax bulk carrier', 46500, 2013, 'A', 'bs_grain', 0.10],
  ['LYMAN WIND', 9000029, 'Palau', 'bulk', 'Panamax bulk carrier', 74200, 2007, 'A', 'bs_grain', 0.60],
  ['KAVKAZ PIONEER', 9000031, 'Russia', 'other', 'Ro-ro cargo ship', 9000, 2003, 'A', 'bs_gen', 0.50],
  ['AEGEAN GLORY', 9000032, 'Malta', 'container', 'Container ship · 3,500 TEU', 48000, 2012, 'A', 'bs_box', 0.05],
  ['BLUE HORIZON', 9000033, 'Panama', 'tanker', 'Aframax crude tanker', 105000, 2008, 'B', 'g_crude', 0.30],
  ['ORYX PEARL', 9000034, 'Marshall Islands', 'tanker', 'VLCC', 300000, 2014, 'B', 'g_crude', 0.10],
  ['AL BATINAH', 9000035, 'Oman', 'bulk', 'Supramax bulk carrier', 57000, 2011, 'B', 'g_bulk', 0.10],
  ['HORMUZ QUEEN', 9000036, 'Gabon', 'tanker', 'MR product tanker', 46000, 2003, 'B', 'g_prod', 0.95, { ex: ['SEA PROSPER'], sanctions: [['OFAC SDN', '2026-02-11', 'IRAN-EO13902'], ['UK', '2026-03-30', 'Iran (Sanctions) Regulations']], hist: [['name', 'SEA PROSPER', 'HORMUZ QUEEN', 8], ['flag', 'Panama', 'Gabon', 8], ['mmsi', '352', null, 8]], opaque: true }],
  ['GULF CRESCENT', 9000037, 'Liberia', 'container', 'Container ship · 5,000 TEU', 65000, 2016, 'B', 'g_box', 0.05],
  ['DHOW SPIRIT', 9000038, 'UAE', 'other', 'General cargo ship', 12000, 2005, 'B', 'g_bulk', 0.50],
  ['MUSANDAM TRADER', 9000039, 'Panama', 'bulk', 'Handysize bulk carrier', 35000, 2009, 'B', 'g_bulk', 0.20],
  ['ZAGROS GLORY', 9000041, 'Iran', 'bulk', 'Panamax bulk carrier', 76000, 2010, 'B', 'g_bulk', 0.70],
  ['ARABIAN FALCON', 9000042, 'Qatar', 'gas', 'LNG carrier · 174,000 m³', 95000, 2019, 'B', 'g_gas', 0.05],
  ['SOHAR SUN', 9000043, 'Oman', 'bulk', 'Supramax bulk carrier', 58000, 2018, 'B', 'g_bulk', 0.10],
  ['DESERT ROSE', 9000044, 'Marshall Islands', 'tanker', 'LR2 product tanker', 110000, 2012, 'B', 'g_prod', 0.45],
  ['TIGRIS STAR', 9000045, 'Panama', 'container', 'Feeder container ship · 1,400 TEU', 20000, 2007, 'B', 'g_box', 0.15],
  ['KHALIJ MOON', 9000046, 'Cameroon', 'tanker', 'Aframax crude tanker', 108000, 2004, 'B', 'g_crude', 0.90, { sanctions: [['EU', '2026-01-26', 'Reg. 267/2012'], ['UK', '2026-02-14', 'Iran (Sanctions) Regulations']], hist: [['mmsi', '626', null, 3], ['flag', 'Gabon', 'Cameroon', 3]], opaque: true }],
  ['DUQM HORIZON', 9000047, 'Oman', 'bulk', 'Ultramax bulk carrier', 62000, 2021, 'B', 'g_bulk', 0.05],
  ['INDUS GRAIN', 9000048, 'India', 'bulk', 'Handymax bulk carrier', 48000, 2006, 'B', 'g_bulk', 0.55],
  ['PEARL OF SALALAH', 9000049, 'Singapore', 'container', 'Container ship · 8,000 TEU', 90000, 2015, 'B', 'g_box', 0.05],
  ['QATARI BREEZE', 9000051, 'Marshall Islands', 'gas', 'LPG carrier · 82,000 m³', 54000, 2013, 'B', 'g_gas', 0.10],
  ['RUB AL KHALI', 9000052, 'UAE', 'tanker', 'MR product tanker', 50000, 2016, 'B', 'g_prod', 0.15],
  ['BANDAR WIND', 9000053, 'Palau', 'other', 'General cargo ship', 7500, 2000, 'B', 'g_bulk', 0.80, { ex: ['NORTHERN LARK'], hist: [['name', 'NORTHERN LARK', 'BANDAR WIND', 5], ['flag', 'Sierra Leone', 'Palau', 5], ['mmsi', '667', null, 5]] }],
  ['SUR LEGACY', 9000054, 'Panama', 'bulk', 'Handysize bulk carrier', 32000, 2008, 'B', 'g_bulk', 0.20],
];

function particulars(type, sub, dwt) {
  const s = sub.toLowerCase();
  const pick = (gt, loa, beam) => ({ gt, loa, beam });
  if (type === 'bulk') return s.includes('handysize') ? pick(22000, 180, 30) : s.includes('handymax') ? pick(27500, 190, 30) : s.includes('supramax') ? pick(32000, 190, 32.3) : s.includes('ultramax') ? pick(36000, 200, 32.3) : s.includes('kamsarmax') ? pick(44500, 229, 32.3) : pick(41000, 225, 32.3);
  if (type === 'tanker') return s.includes('vlcc') ? pick(160000, 333, 60) : s.includes('suezmax') ? pick(83000, 274, 48) : s.includes('aframax') || s.includes('lr2') ? pick(60000, 250, 44) : pick(29500, 183, 32.2);
  if (type === 'container') return dwt > 80000 ? pick(95000, 335, 43) : dwt > 60000 ? pick(55000, 294, 32.2) : dwt > 40000 ? pick(40000, 230, 32.2) : dwt > 30000 ? pick(28000, 210, 30) : dwt > 22000 ? pick(20000, 175, 28) : pick(17000, 170, 27);
  if (type === 'gas') return s.includes('lng') ? pick(115000, 295, 46) : pick(48000, 230, 36);
  return s.includes('ro-ro') ? pick(12000, 150, 23) : dwt > 10000 ? pick(8000, 140, 20) : pick(3800, 100, 16);
}
function draughts(type, dwt) {
  if (type === 'bulk') return dwt > 70000 ? [14.2, 7.2] : dwt > 55000 ? [12.6, 6.6] : dwt > 40000 ? [11.4, 6.0] : [10.2, 5.6];
  if (type === 'tanker') return dwt > 250000 ? [20.6, 11.0] : dwt > 140000 ? [17.0, 9.0] : dwt > 90000 ? [14.9, 8.1] : [11.8, 6.4];
  if (type === 'gas') return dwt > 80000 ? [11.8, 9.6] : [11.0, 8.4];
  if (type === 'container') return dwt > 80000 ? [14.0, 11.5] : dwt > 40000 ? [12.5, 10.0] : [10.5, 8.2];
  return dwt > 10000 ? [8.2, 4.6] : [6.4, 3.8];
}
const FLEET = FLEET_DEF.map(row => {
  const [name, imo, flag, type, sub, dwt, built, region, trade, risk, opts = {}] = row;
  const rng = mulberry32(imo * 7919), mids = MID[flag] || ['352'];
  const d6 = () => String(Math.floor(rng() * 900000) + 100000);
  const mmsi = mids[Math.floor(rng() * mids.length)] + d6();
  const callsign = (CALL[flag] || '3F') + String.fromCharCode(65 + Math.floor(rng() * 26)) + String(Math.floor(rng() * 90) + 10) + String.fromCharCode(65 + Math.floor(rng() * 26));
  const part = particulars(type, sub, dwt), dr = draughts(type, dwt);
  const cos = opts.opaque ? OPAQUE : CO[region];
  const co = cos[Math.floor(rng() * cos.length)], co2 = cos[Math.floor(rng() * cos.length)];
  const history = (opts.hist || []).map(([field, from, to, monthsAgo]) => ({ field, from: field === 'mmsi' ? from + d6() : from, to: field === 'mmsi' ? mmsi : to, t: NOW - monthsAgo * 30.4 * D - Math.floor(rng() * 10) * D }));
  const sanctions = (opts.sanctions || []).map(([list, date, programme]) => ({ list, programme, t: Date.parse(date + 'T00:00:00Z') }));
  const builders = BUILDERS[type];
  return {
    name, imo, flag, type, sub, dwt, built, region, trade, risk, mmsi, callsign, ...part,
    draughtLoaded: dr[0], draughtBallast: dr[1], exNames: opts.ex || [], history, sanctions,
    builder: builders[Math.floor(rng() * builders.length)],
    classSoc: risk > 0.8 ? (rng() < 0.5 ? 'Not IACS · register unverified' : 'Withdrawn from IACS class (2025)') : IACS[Math.floor(rng() * IACS.length)],
    pi: risk > 0.8 ? 'Non-IG insurer · cover unverified' : IG_PI[Math.floor(rng() * IG_PI.length)],
    regOwner: `${co[0]} (${co[1]})`,
    benOwner: opts.opaque ? 'Not identified · nominee director' : `${co[0]} group`,
    ism: opts.opaque ? `${co2[0]} (${co2[1]})` : `${co2[0]} (${co2[1]})`,
    operator: opts.opaque ? 'Undisclosed' : `${co[0]} (${co[1]})`,
    speed: type === 'container' ? 15 + rng() * 4 : type === 'gas' ? 15 + rng() * 2 : type === 'other' ? 9 + rng() * 2 : 11 + rng() * 2.3,
  };
});
const BY_IMO = Object.fromEntries(FLEET.map(v => [v.imo, v])); // server mode adds entries as vessels load

/* --------------------------------- mock AIS provider ---------------------------------
   Same three methods the brief asks for: search_vessel, get_track, get_vessels_near.
   A real provider (Kpler/MarineTraffic, Spire, Datalastic, VesselFinder) replaces this
   object without touching the engine or the screens. --------------------------------- */
const MockProvider = {
  name: 'Mock AIS provider (generated tracks)',
  _tracks: new Map(), _sts: [], _static: new Map(),
  searchVessel(q) {
    const s = q.trim().toUpperCase(); if (!s) return [];
    return FLEET.filter(v => v.name.includes(s) || String(v.imo).startsWith(s) || v.mmsi.startsWith(s) || v.exNames.some(n => n.includes(s))).slice(0, 12);
  },
  getTrack(imo, start, end) {
    if (!this._tracks.has(imo)) this._generate(BY_IMO[imo]);
    return this._tracks.get(imo).filter(p => p.t >= start && p.t <= end);
  },
  getVesselsNear(lat, lon, radiusM, t0, t1) {
    const rNm = radiusM / 1852;
    return this._sts.filter(e => e.t0 < t1 && e.t1 > t0 && nmDist(lat, lon, e.lat, e.lon) <= rNm + 0.05)
      .map(e => ({ vessel: BY_IMO[e.partner], t0: Math.max(e.t0, t0), t1: Math.min(e.t1, t1), lat: e.lat, lon: e.lon }));
  },
  getStatic(imo) { if (!this._static.has(imo)) this._generate(BY_IMO[imo]); return this._static.get(imo); },
  fleetPositions() { return FLEET.map(v => { const tr = this.getTrack(v.imo, NOW - YEAR, NOW); return { v, last: tr[tr.length - 1], static: this.getStatic(v.imo) }; }); },

  _generate(v) {
    const rng = mulberry32(v.imo);
    const kinds = { tanker: 'tanker', bulk: 'bulk', container: 'container', gas: 'gas', other: 'any' };
    const fits = p => p.k.includes(kinds[v.type]) || p.k.includes('any') || (v.type === 'other' && p.k.includes('bulk'));
    const trade = TRADES[v.trade].map(id => PORT[id]);
    const sens = SENSITIVE_PORTS[v.region].map(id => PORT[id]).filter(fits);
    const pick = arr => arr[Math.floor(rng() * arr.length)];
    const liquid = v.type === 'tanker' || v.type === 'bulk' || v.type === 'gas';
    const T0 = NOW - YEAR - (12 + rng() * 25) * D;
    // ---- phase 1: port sequence with legs until the calendar passes "now" ----
    let t = T0, cur = pick(trade), sensLeft = v.risk < 0.3 ? 0 : v.risk < 0.6 ? 1 : 1 + Math.floor(v.risk * 3), legs = [];
    while (t < NOW + 20 * D) {
      const stayH = v.type === 'container' ? 14 + rng() * 26 : v.type === 'gas' ? 24 + rng() * 40 : 48 + rng() * 150;
      let next; do { next = (sensLeft > 0 && rng() < v.risk * 0.3 && sens.length) ? pick(sens) : pick(trade); } while (next.id === cur.id);
      if (next.zone) sensLeft--;
      const anchorH = next.anch && rng() < (v.type === 'container' ? 0.3 : 0.55) ? (v.type === 'container' ? 6 + rng() * 40 : 10 + rng() * 130) : 0;
      const route = seaRoute(v.region, cur.an, next.an);
      const path = [cur.b, cur.a, ...route.pts.slice(1, -1), next.a];
      let nmTotal = 0; for (let i = 1; i < path.length; i++) nmTotal += nmDist(path[i - 1][1], path[i - 1][0], path[i][1], path[i][0]);
      const speed = v.speed * (0.92 + rng() * 0.16);
      const leg = { from: cur, to: next, stayH, anchorH, path, nm: nmTotal, speed, events: [], tStart: t };
      t += stayH * H + nmTotal / speed * H + anchorH * H + 2 * H;
      leg.tEnd = t; legs.push(leg);
      cur = next;
    }
    // ---- phase 2: plant events by risk profile (only on legs that have happened) ----
    const nGaps = v.risk < 0.25 ? (rng() < 0.45 ? 1 : 0) : v.risk < 0.6 ? 1 + (rng() < 0.5 ? 1 : 0) : 2 + Math.floor(rng() * 2);
    const nDr = v.risk < 0.4 ? 0 : (rng() < v.risk ? 1 : 0) + (v.risk > 0.8 ? 1 : 0);
    const nSts = v.risk < 0.4 ? 0 : (rng() < v.risk ? 1 : 0) + (v.risk > 0.85 && rng() < 0.6 ? 1 : 0);
    const nJump = Math.floor(rng() * 2.4);
    const longLegs = legs.filter(l => l.nm / l.speed > 14 && l.tEnd < NOW - 2 * D && !l.events.length);
    const sensLegs = longLegs.filter(l => l.to.zone || l.from.zone);
    const take = pool => { const free = pool.filter(l => !l.events.length); return free.length ? pick(free) : null; };
    const choose = (pref, type, payload) => { const leg = (pref.length && rng() < 0.8 ? take(pref) : null) || take(longLegs); if (leg) leg.events.push({ type, ...payload }); return leg; };
    for (let i = 0; i < nGaps; i++) choose(sensLegs, 'gap', { hours: v.risk > 0.6 ? 18 + rng() * 40 : 7 + rng() * 14, at: 0.25 + rng() * 0.5 });
    const stsLegs = [];
    for (let i = 0; i < nSts; i++) { const partners = FLEET.filter(o => o.imo !== v.imo && o.region === v.region && (v.type !== 'tanker' || o.type === 'tanker')); const leg = choose([], 'sts', { hours: 2.5 + rng() * 5, at: 0.3 + rng() * 0.4, partner: pick(partners).imo }); if (leg) stsLegs.push(leg); }
    for (let i = 0; i < nDr; i++) { const leg = stsLegs.length && rng() < 0.8 ? stsLegs.shift() : take(longLegs); if (leg) leg.events.push({ type: 'draught', at: 0.3 + rng() * 0.4, delta: 1.3 + rng() * 2.8 }); }
    for (let i = 0; i < nJump; i++) choose([], 'jump', { at: 0.2 + rng() * 0.6, nm: 45 + rng() * 60 });
    // ---- phase 3: emit AIS positions ----
    const pts = [], stsReg = [];
    let loaded = rng() < 0.5, draught = loaded ? v.draughtLoaded : v.draughtBallast;
    const jitter = () => (rng() - 0.5) * 16 * 60e3;
    const portsR = GEO.regions[v.region].ports;
    const srcOf = (lat, lon) => { for (const p of portsR) { if (Math.abs(lat - p.b[1]) < 0.75 && Math.abs(lon - p.b[0]) < 0.9 && nmDist(lat, lon, p.b[1], p.b[0]) < 45) return 'T'; } return 'S'; };
    const emit = (tt, lat, lon, sog, cog, nav) => { pts.push({ t: tt, lat, lon, sog: +sog.toFixed(1), cog: Math.round((cog + 360) % 360), draught: +draught.toFixed(1), nav, src: srcOf(lat, lon) }); if (rng() < 0.003) pts.push({ ...pts[pts.length - 1] }); if (rng() < 0.0006) pts.push({ ...pts[pts.length - 1], t: tt + 60e3, lat: 91, lon }); };
    const transitH = (a, b) => Math.max(1, nmDist(a[1], a[0], b[1], b[0]) / 6);
    let status = null;
    t = T0;
    for (const leg of legs) {
      // alongside at the departure port
      for (let h = 0; h < leg.stayH; h += 3) emit(t + h * H + jitter(), leg.from.b[1] + (rng() - 0.5) * 0.0012, leg.from.b[0] + (rng() - 0.5) * 0.0012, 0, 90 + rng() * 180, 5);
      if (t + leg.stayH * H > NOW) { status = { state: 'moored', port: leg.from, lastPort: leg.from, nextPort: leg.to, destination: leg.to.name.toUpperCase(), eta: null, since: t }; break; }
      t += leg.stayH * H + 0.5 * H;
      if (liquid) { loaded = !loaded; draught = (loaded ? v.draughtLoaded : v.draughtBallast) + (rng() - 0.5) * 0.4; } else draught += (rng() - 0.5) * 0.8;
      // underway along the path
      const seg = []; let total = 0;
      for (let i = 1; i < leg.path.length; i++) { const d = nmDist(leg.path[i - 1][1], leg.path[i - 1][0], leg.path[i][1], leg.path[i][0]); seg.push({ a: leg.path[i - 1], b: leg.path[i], d, start: total }); total += d; }
      const posAt = dist => { const s = seg.find(s => dist <= s.start + s.d) || seg[seg.length - 1]; const f = Math.max(0, Math.min(1, (dist - s.start) / (s.d || 1))); return { lat: s.a[1] + (s.b[1] - s.a[1]) * f, lon: s.a[0] + (s.b[0] - s.a[0]) * f, cog: bearing(s.a[1], s.a[0], s.b[1], s.b[0]) }; };
      const legH = total / leg.speed, ev = leg.events;
      const gap = ev.find(e => e.type === 'gap'), sts = ev.find(e => e.type === 'sts'), dch = ev.find(e => e.type === 'draught'), jump = ev.find(e => e.type === 'jump');
      const gapH0 = gap ? gap.at * legH : -1, gapH1 = gap ? gapH0 + gap.hours : -1;
      const stsH = sts ? sts.at * legH : -1, drH = dch ? (sts ? stsH + sts.hours + 0.5 : dch.at * legH) : -1, jmpH = jump ? jump.at * legH : -1;
      let tLeg = t, stsDone = false, drDone = false, jmpDone = false, cut = false;
      const dest = (v.risk > 0.8 && rng() < 0.5) ? 'FOR ORDERS' : leg.to.name.toUpperCase();
      leg.depart = t;
      for (let h = 0; h <= legH; h += 1) {
        const p = posAt(h * leg.speed);
        if (sts && !stsDone && h >= stsH) { // deviate to the nearest known STS area, stop, resume
          const area = GEO.sts.map(a => ({ a, d: nmDist(p.lat, p.lon, a.lonlat[1], a.lonlat[0]) })).sort((x, y) => x.d - y.d)[0];
          const [slat, slon] = area.d < 90 ? [area.a.lonlat[1], area.a.lonlat[0]] : [p.lat, p.lon];
          const tr = area.d < 90 ? Math.ceil(area.d / leg.speed) : 0;
          for (let k = 1; k <= tr; k++) { const f = k / tr; emit(tLeg + k * H + jitter(), p.lat + (slat - p.lat) * f, p.lon + (slon - p.lon) * f, leg.speed, bearing(p.lat, p.lon, slat, slon), 0); }
          tLeg += tr * H + H; const t0 = tLeg;
          for (let k = 0; k <= sts.hours; k += 0.5) emit(tLeg + k * H + jitter() / 4, slat + (rng() - 0.5) * 0.0008, slon + (rng() - 0.5) * 0.0008, 0.2 + rng() * 0.4, rng() * 360, 0);
          tLeg += sts.hours * H + H;
          stsReg.push({ imo: v.imo, partner: sts.partner, lat: slat, lon: slon, t0, t1: tLeg - H, area: area.a.name });
          for (let k = 1; k <= tr; k++) { const f = k / tr; emit(tLeg + k * H + jitter(), slat + (p.lat - slat) * f, slon + (p.lon - slon) * f, leg.speed, bearing(slat, slon, p.lat, p.lon), 0); }
          tLeg += tr * H; stsDone = true;
        }
        if (dch && !drDone && h >= drH) { draught += loaded ? -dch.delta : dch.delta; drDone = true; }
        if (gap && h >= gapH0 && h < gapH1) { tLeg += H; if (tLeg > NOW) { cut = true; break; } continue; }
        if (jump && !jmpDone && h >= jmpH) { const [jlat, jlon] = destPoint(p.lat, p.lon, rng() * 360, jump.nm); emit(tLeg + 0.5 * H, jlat, jlon, leg.speed, p.cog, 0); jmpDone = true; }
        emit(tLeg + jitter(), p.lat, p.lon, leg.speed + (rng() - 0.5) * 0.8, p.cog + (rng() - 0.5) * 6, 0);
        tLeg += H;
        if (tLeg > NOW) { cut = true; break; }
      }
      if (cut) { const rem = Math.max(0, total - (tLeg - t) / H * leg.speed); status = { state: 'underway', port: null, lastPort: leg.from, nextPort: leg.to, destination: dest, eta: NOW + rem / leg.speed * H, since: leg.depart }; break; }
      t = tLeg; leg.arrive = t;
      // arrival: wait at the anchorage if the port has one and a wait was planned, then shift to the berth
      let pos = leg.path[leg.path.length - 1];
      if (leg.anchorH) {
        const [alon, alat, ar] = leg.to.anch; const [plat, plon] = destPoint(alat, alon, rng() * 360, rng() * ar * 0.6);
        t += transitH(pos, [plon, plat]) * H;
        for (let h = 0; h < leg.anchorH; h += 3) emit(t + h * H + jitter(), plat + (rng() - 0.5) * 0.002, plon + (rng() - 0.5) * 0.002, rng() * 0.2, rng() * 360, 1);
        if (t + leg.anchorH * H > NOW) { status = { state: 'anchored', port: leg.to, lastPort: leg.from, nextPort: leg.to, destination: dest, eta: null, since: t }; break; }
        t += leg.anchorH * H + 0.5 * H; pos = [plon, plat];
      }
      t += transitH(pos, leg.to.b) * H;
    }
    const track = pts.filter(p => p.t <= NOW).sort((a, b) => a.t - b.t);
    const lastLeg = legs[legs.length - 1];
    this._tracks.set(v.imo, track); this._sts.push(...stsReg); this._static.set(v.imo, status || { state: 'moored', port: lastLeg.to, lastPort: lastLeg.from, nextPort: null, destination: '', eta: null, since: NOW - D });
  },
};
const Provider = MockProvider;

/* ------------------------------ port calls & voyages ------------------------------ */
function matchPort(lat, lon, region) {
  let best = null, bd = Infinity;
  for (const p of GEO.regions[region].ports) { const d = nmDist(lat, lon, p.b[1], p.b[0]); if (d < bd) { bd = d; best = p; } }
  if (best && bd <= RULES.portCall.portRadiusNm) return { port: best, anchorage: false, nm: bd };
  for (const p of GEO.regions[region].ports) if (p.anch && nmDist(lat, lon, p.anch[1], p.anch[0]) <= p.anch[2]) return { port: p, anchorage: true, nm: nmDist(lat, lon, p.b[1], p.b[0]) };
  const z = zoneAt(lon, lat);
  if (z) return { port: { id: 'Z-' + z.id, name: 'Anchorage · ' + z.name, c: '', b: [lon, lat], zone: z.id, pseudo: true }, anchorage: true, nm: 0 };
  return null;
}
function detectPortCalls(track, region) {
  const calls = []; let i = 0;
  while (i < track.length) {
    if (track[i].sog < RULES.portCall.maxSpeedKn) {
      let j = i; while (j + 1 < track.length && track[j + 1].sog < RULES.portCall.maxSpeedKn && track[j + 1].t - track[j].t < 12 * H) j++;
      if (track[j].t - track[i].t >= RULES.portCall.minHours * H || j === track.length - 1) {
        const mid = track[Math.floor((i + j) / 2)], m = matchPort(mid.lat, mid.lon, region);
        if (m) calls.push({ port: m.port, anchorage: m.anchorage, arrive: track[i].t, depart: track[j].t, lat: mid.lat, lon: mid.lon, i0: i, i1: j, draughtIn: track[i].draught, draughtOut: track[j].draught, anchHours: m.anchorage ? (track[j].t - track[i].t) / H : 0 });
      }
      i = j + 1;
    } else i++;
  }
  const merged = [];
  for (const c of calls) {
    const last = merged[merged.length - 1];
    if (last && last.port.id === c.port.id && c.arrive - last.depart < RULES.portCall.mergeWithinHours * H && (last.anchorage || c.anchorage)) {
      last.depart = c.depart; last.i1 = c.i1; last.draughtOut = c.draughtOut; last.anchHours += c.anchHours;
      if (last.anchorage && !c.anchorage) { last.anchorage = false; last.lat = c.lat; last.lon = c.lon; }
    } else merged.push({ ...c });
  }
  return merged;
}
function splitVoyages(track, calls) {
  const voy = [];
  const add = (from, to, i0, i1) => {
    const pts = track.slice(i0, i1 + 1); if (pts.length < 2) return;
    let nm = 0; for (let k = 1; k < pts.length; k++) if (!pts[k].jump && !pts[k - 1].jump) nm += nmDist(pts[k - 1].lat, pts[k - 1].lon, pts[k].lat, pts[k].lon);
    const depart = from ? from.depart : pts[0].t, arrive = to ? to.arrive : null;
    voy.push({ from, to, i0, i1, pts, depart, arrive, nm: Math.round(nm), draughtOut: pts[Math.min(2, pts.length - 1)].draught, draughtIn: pts[pts.length - 1].draught, current: !to, flags: [], darkH: 0 });
  };
  if (!calls.length) { add(null, null, 0, track.length - 1); }
  else {
    if (calls[0].i0 > 3) add(null, calls[0], 0, calls[0].i0);
    for (let k = 0; k + 1 < calls.length; k++) add(calls[k], calls[k + 1], calls[k].i1, calls[k + 1].i0);
    const last = calls[calls.length - 1];
    if (track.length - 1 - last.i1 > 3) add(last, null, last.i1, track.length - 1);
  }
  voy.forEach((vg, i) => { vg.n = i + 1; vg.color = i % 8; });
  return voy;
}

/* ----------------------------------- rule engine ----------------------------------- */
const RULE_LIST = [
  { id: 'sanctions', name: 'Sanctions hit', run(c) {
    const hits = c.v.sanctions.filter(s => s.t <= NOW && s.t >= NOW - RULES.sanctions.lookbackMonths * 30.4 * D);
    if (!hits.length) return [];
    return [{ rule: 'Sanctions hit', severity: 'high', vesselLevel: true, t0: hits[0].t, title: `IMO ${c.v.imo} on ${hits.map(h => h.list).join(' and ')} list${hits.length > 1 ? 's' : ''}`,
      lines: hits.map(h => `${h.list} · listed ${fmtDY(h.t)} · ${h.programme}`).concat(['Screened against OFAC SDN, EU and UK consolidated lists (sample lists)']) }];
  } },
  { id: 'sensitive_port', name: 'Call at a sensitive port', run(c) {
    return c.portCalls.filter(pc => (pc.port.zone && ZONE[pc.port.zone].enabled !== false) || zoneAt(pc.lon, pc.lat)).map(pc => {
      const z = (pc.port.zone && ZONE[pc.port.zone].enabled !== false) ? ZONE[pc.port.zone] : zoneAt(pc.lon, pc.lat);
      return { rule: 'Call at a sensitive port', severity: 'high', t0: pc.arrive, t1: pc.depart, lat: pc.lat, lon: pc.lon, portCall: pc,
        title: `${pc.anchorage ? 'Anchored' : 'Called'} at ${pc.port.name}`,
        lines: [`${z.name} · ${z.basis}`, `Arrived ${fmtDT(pc.arrive)}, departed ${fmtDT(pc.depart)} ${TZ()} · ${fmtDur(pc.depart - pc.arrive)}`, `Draught in ${pc.draughtIn} m · out ${pc.draughtOut} m`] };
    });
  } },
  { id: 'ais_gap', name: 'AIS gap', run(c) {
    const out = [];
    for (let i = 1; i < c.track.length; i++) {
      const a = c.track[i - 1], b = c.track[i], dt = b.t - a.t;
      if (dt < RULES.aisGap.minHours * H || c.inPort[i - 1] || c.inPort[i]) continue;
      const nz = nearestZone(a.lon, a.lat), hours = dt / H;
      const high = hours > RULES.aisGap.highHours || nz.nm <= RULES.aisGap.nearSensitiveNm;
      out.push({ rule: 'AIS gap', severity: high ? 'high' : 'medium', t0: a.t, t1: b.t, lat: a.lat, lon: a.lon, hours, idx: i,
        title: `AIS gap of ${Math.round(hours)} hours`,
        lines: [`Off ${fmtDT(a.t)}, back on ${fmtDT(b.t)} ${TZ()}`, `Last position ${fmtDM(a.lat, a.lon)} · ${Math.round(nz.nm)} nm from ${nz.zone.name}`, `Reappeared ${Math.round(nmDist(a.lat, a.lon, b.lat, b.lon))} nm away · ${a.src === 'S' ? 'satellite' : 'terrestrial'} AIS before the gap`],
        evidence: { before: c.track.slice(Math.max(0, i - 3), i), after: c.track.slice(i, i + 3) } });
    }
    return out;
  } },
  { id: 'draught', name: 'Draught change at sea', run(c) {
    const out = [];
    for (let i = 1; i < c.track.length; i++) {
      const a = c.track[i - 1], b = c.track[i], d = b.draught - a.draught;
      if (Math.abs(d) < RULES.draughtChange.minMeters || c.inPort[i - 1] || c.inPort[i] || b.jump) continue;
      const np = nearestPort(b.lon, b.lat, c.v.region);
      out.push({ rule: 'Draught change at sea', severity: 'high', t0: b.t, t1: b.t, lat: b.lat, lon: b.lon,
        title: `Draught ${d > 0 ? '+' : ''}${d.toFixed(1)} m at sea`,
        lines: [`${fmtDT(b.t)} ${TZ()} · ${fmtDM(b.lat, b.lon)} · ${Math.round(np.nm)} nm from ${np.port.name}`, `Reported draught ${a.draught} m → ${b.draught} m with no port call in between`, 'Draught is typed in by the crew: indicator, not proof'],
        evidence: { before: c.track.slice(Math.max(0, i - 3), i), after: c.track.slice(i, i + 3) } });
    }
    return out;
  } },
  { id: 'sts', name: 'Possible ship-to-ship transfer', run(c) {
    const out = []; let i = 0;
    while (i < c.track.length) {
      if (c.track[i].sog < RULES.sts.maxSpeedKn && !c.inPort[i]) {
        let j = i; while (j + 1 < c.track.length && c.track[j + 1].sog < RULES.sts.maxSpeedKn && !c.inPort[j + 1] && c.track[j + 1].t - c.track[j].t < 6 * H) j++;
        const t0 = c.track[i].t, t1 = c.track[j].t;
        if (t1 - t0 >= RULES.sts.minHours * H) {
          const mid = c.track[Math.floor((i + j) / 2)];
          for (const n of Provider.getVesselsNear(mid.lat, mid.lon, RULES.sts.maxDistM, t0, t1)) {
            if (n.vessel.imo === c.v.imo || n.t1 - n.t0 < RULES.sts.minHours * H) continue;
            const np = nearestPort(mid.lon, mid.lat, c.v.region);
            out.push({ rule: 'Possible ship-to-ship transfer', severity: 'high', t0, t1, lat: mid.lat, lon: mid.lon, partner: n.vessel,
              title: `Possible STS with ${n.vessel.name}`,
              lines: [`${fmtDT(t0)} – ${fmtDT(t1)} ${TZ()} · ${fmtDur(t1 - t0)} both under ${RULES.sts.maxSpeedKn} kn, within ${RULES.sts.maxDistM} m`, `${n.vessel.name} · IMO ${n.vessel.imo} · ${n.vessel.flag} · ${n.vessel.sub}`, `${fmtDM(mid.lat, mid.lon)} · ${Math.round(np.nm)} nm from ${np.port.name}, outside port limits`],
              evidence: { before: c.track.slice(Math.max(0, i - 2), i + 1), after: c.track.slice(j, j + 3) } });
          }
        }
        i = j + 1;
      } else i++;
    }
    return out;
  } },
  { id: 'jump', name: 'Position jump', run(c) {
    const out = [];
    for (let i = 1; i < c.track.length; i++) {
      const a = c.track[i - 1], b = c.track[i], dt = (b.t - a.t) / H; if (dt <= 0) continue;
      const kn = nmDist(a.lat, a.lon, b.lat, b.lon) / dt;
      if (kn > RULES.positionJump.maxImpliedKn) {
        const jam = jammingAt(b.lon, b.lat); b.jump = true;
        out.push({ rule: 'Position jump', severity: 'medium', t0: b.t, t1: b.t, lat: b.lat, lon: b.lon,
          title: `Position jump, ${Math.round(kn)} knots`,
          lines: [`${fmtDT(b.t)} ${TZ()} · fix at ${fmtDM(b.lat, b.lon)}, ${Math.round(nmDist(a.lat, a.lon, b.lat, b.lon))} nm from the previous fix ${(dt * 60).toFixed(0)} min earlier`, jam ? `Inside a known GPS jamming area (${jam.name}) · possible GPS jamming` : 'Outside known jamming areas · check the receiver'],
          evidence: { before: c.track.slice(Math.max(0, i - 2), i), after: c.track.slice(i, i + 3) } });
        i++; // the return fix belongs to the same event
      }
    }
    return out;
  } },
  { id: 'identity', name: 'Identity change', run(c) {
    const ch = c.v.history.filter(h => h.t >= NOW - YEAR).sort((a, b) => a.t - b.t);
    if (!ch.length) return [];
    const label = { name: 'Name', flag: 'Flag', mmsi: 'MMSI' };
    return [{ rule: 'Identity change', severity: ch.length > RULES.identity.mediumIfMoreThan ? 'medium' : 'info', vesselLevel: true, t0: ch[0].t,
      title: `${ch.length} identity change${ch.length > 1 ? 's' : ''} in 12 months`, lines: ch.map(h => `${fmtDY(h.t)} · ${label[h.field]} ${h.from} → ${h.to}`) }];
  } },
];

const ANALYSIS = new Map();
function analyze(v) {
  if (ANALYSIS.has(v.imo)) return ANALYSIS.get(v.imo);
  const t0 = (typeof performance !== 'undefined' ? performance : Date).now();
  const raw = Provider.getTrack(v.imo, NOW - YEAR, NOW);
  const seen = new Set(), track = []; let dup = 0, bad = 0;
  for (const p of raw) {
    if (!Number.isFinite(p.lat) || !Number.isFinite(p.lon) || Math.abs(p.lat) > 90 || Math.abs(p.lon) > 180) { bad++; continue; }
    if (seen.has(p.t)) { dup++; continue; }
    seen.add(p.t); track.push({ ...p });
  }
  const portCalls = detectPortCalls(track, v.region);
  const inPort = new Uint8Array(track.length);
  for (const pc of portCalls) for (let i = pc.i0; i <= pc.i1; i++) inPort[i] = 1;
  const ctx = { v, track, portCalls, inPort };
  const flags = RULE_LIST.flatMap(r => r.run(ctx));
  const voyages = splitVoyages(track, portCalls);
  flags.forEach((f, i) => { f.id = v.imo + '-' + i; f.vessel = v; });
  for (const f of flags) {
    if (f.vesselLevel) continue;
    let vg = f.portCall ? voyages.find(x => x.to === f.portCall) : voyages.find(x => f.t0 >= x.depart - H && (x.arrive === null || f.t0 <= x.arrive + H));
    if (!vg) vg = voyages[voyages.length - 1];
    if (vg) { f.voyage = vg; vg.flags.push(f); if (f.rule === 'AIS gap') vg.darkH += f.hours; }
  }
  const sev = { high: 0, medium: 0, info: 0 }; flags.forEach(f => sev[f.severity]++);
  const last = track[track.length - 1], st = Provider.getStatic(v.imo);
  const res = { v, track, portCalls, voyages, flags, sev, last, static: st,
    stats: { raw: raw.length, dup, bad, clean: track.length, portCalls: portCalls.length, voyages: voyages.length, flags: flags.length, ms: Math.round((typeof performance !== 'undefined' ? performance : Date).now() - t0) } };
  ANALYSIS.set(v.imo, res);
  return res;
}
