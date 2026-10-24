/* PMTiles v3 reader as a MapLibre protocol: `pmtiles://<url>` sources read tiles straight out of one
   file with HTTP range requests, so the server needs no tile server — the web server's static file is enough.
   A compact port of the reference reader in protomaps/PMTiles (BSD 3-Clause, © Protomaps LLC):
   header, varint directories, Hilbert tile ids, leaf directories, gzip via DecompressionStream. */
'use strict';
(function () {
  const HEADER = 127;

  function toNum(low, high) { return (high >>> 0) * 0x100000000 + (low >>> 0); }
  function readVarintRemainder(l, p) {
    const buf = p.buf; let b = buf[p.pos++]; let h = (b & 0x70) >> 4;
    if (b < 0x80) return toNum(l, h);
    b = buf[p.pos++]; h |= (b & 0x7f) << 3; if (b < 0x80) return toNum(l, h);
    b = buf[p.pos++]; h |= (b & 0x7f) << 10; if (b < 0x80) return toNum(l, h);
    b = buf[p.pos++]; h |= (b & 0x7f) << 17; if (b < 0x80) return toNum(l, h);
    b = buf[p.pos++]; h |= (b & 0x7f) << 24; if (b < 0x80) return toNum(l, h);
    b = buf[p.pos++]; h |= (b & 0x01) << 31; if (b < 0x80) return toNum(l, h);
    throw new Error('varint too long');
  }
  function readVarint(p) {
    const buf = p.buf; let b = buf[p.pos++]; let val = b & 0x7f;
    if (b < 0x80) return val;
    b = buf[p.pos++]; val |= (b & 0x7f) << 7; if (b < 0x80) return val;
    b = buf[p.pos++]; val |= (b & 0x7f) << 14; if (b < 0x80) return val;
    b = buf[p.pos++]; val |= (b & 0x7f) << 21; if (b < 0x80) return val;
    b = buf[p.pos]; val |= (b & 0x0f) << 28;
    return readVarintRemainder(val, p);
  }
  function rotate(n, x, y, rx, ry) {
    if (ry === 0) { if (rx !== 0) return [n - 1 - y, n - 1 - x]; return [y, x]; }
    return [x, y];
  }
  function zxyToTileId(z, x, y) {
    if (z > 26) throw new Error('zoom too large');
    if (x >= 1 << z || y >= 1 << z) throw new Error('tile outside zoom bounds');
    let acc = ((1 << z) * (1 << z) - 1) / 3;
    let a = z - 1; let tx = x, ty = y;
    for (let s = 1 << a; s > 0; s >>= 1) {
      const rx = tx & s, ry = ty & s;
      acc += ((3 * rx) ^ ry) * (1 << a);
      [tx, ty] = rotate(s, tx, ty, rx, ry);
      a--;
    }
    return acc;
  }
  function u64(v, o) { return v.getUint32(o + 4, true) * 2 ** 32 + v.getUint32(o, true); }
  function parseHeader(buf) {
    const v = new DataView(buf);
    if (v.getUint16(0, true) !== 0x4d50) throw new Error('not a PMTiles archive');
    const spec = v.getUint8(7);
    if (spec > 3) throw new Error('PMTiles spec ' + spec + ' not supported');
    return {
      rootOffset: u64(v, 8), rootLength: u64(v, 16), metaOffset: u64(v, 24), metaLength: u64(v, 32),
      leafOffset: u64(v, 40), leafLength: u64(v, 48), dataOffset: u64(v, 56), dataLength: u64(v, 64),
      clustered: v.getUint8(96) === 1, internalCompression: v.getUint8(97), tileCompression: v.getUint8(98), tileType: v.getUint8(99),
      minZoom: v.getUint8(100), maxZoom: v.getUint8(101),
      minLon: v.getInt32(102, true) / 1e7, minLat: v.getInt32(106, true) / 1e7, maxLon: v.getInt32(110, true) / 1e7, maxLat: v.getInt32(114, true) / 1e7,
      centerZoom: v.getUint8(118), centerLon: v.getInt32(119, true) / 1e7, centerLat: v.getInt32(123, true) / 1e7,
    };
  }
  function parseDirectory(buf) {
    const p = { buf: new Uint8Array(buf), pos: 0 };
    const n = readVarint(p);
    const entries = [];
    let last = 0;
    for (let i = 0; i < n; i++) { const v = readVarint(p); entries.push({ tileId: last + v, offset: 0, length: 0, runLength: 1 }); last += v; }
    for (let i = 0; i < n; i++) entries[i].runLength = readVarint(p);
    for (let i = 0; i < n; i++) entries[i].length = readVarint(p);
    for (let i = 0; i < n; i++) {
      const v = readVarint(p);
      entries[i].offset = (v === 0 && i > 0) ? entries[i - 1].offset + entries[i - 1].length : v - 1;
    }
    return entries;
  }
  function findTile(entries, tileId) {
    let m = 0, n = entries.length - 1;
    while (m <= n) {
      const k = (n + m) >> 1; const c = tileId - entries[k].tileId;
      if (c > 0) m = k + 1; else if (c < 0) n = k - 1; else return entries[k];
    }
    if (n >= 0) {
      if (entries[n].runLength === 0) return entries[n];
      if (tileId - entries[n].tileId < entries[n].runLength) return entries[n];
    }
    return null;
  }
  async function decompress(buf, kind) {
    if (kind === 0 || kind === 1) return buf;               // unknown / none
    if (kind === 2) {                                        // gzip
      if (typeof DecompressionStream === 'undefined') throw new Error('gzip not supported by this browser');
      const stream = new Response(buf).body.pipeThrough(new DecompressionStream('gzip'));
      return new Response(stream).arrayBuffer();
    }
    throw new Error('PMTiles compression ' + kind + ' not supported');
  }

  class Archive {
    constructor(url) { this.url = url; this.header = null; this.dirs = new Map(); this.pending = new Map(); this.etag = null; }
    async bytes(offset, length, signal) {
      const r = await fetch(this.url, { headers: { Range: `bytes=${offset}-${offset + length - 1}` }, signal, credentials: 'same-origin' });
      if (offset === 0 && r.status === 416) {
        const cr = r.headers.get('Content-Range') || '';
        const total = +cr.replace('bytes */', '');
        return this.bytes(0, total, signal);
      }
      if (r.status >= 300) throw new Error('tiles HTTP ' + r.status);
      const len = +(r.headers.get('Content-Length') || 0);
      if (r.status === 200 && len > length) throw new Error('the server ignored the byte range');
      return r.arrayBuffer();
    }
    async getHeader() {
      if (this.header) return this.header;
      if (!this._h) {
        this._h = (async () => {
          const buf = await this.bytes(0, 16384);
          const h = parseHeader(buf.slice(0, HEADER));
          const root = parseDirectory(await decompress(buf.slice(h.rootOffset, h.rootOffset + h.rootLength), h.internalCompression));
          this.dirs.set(`${h.rootOffset}:${h.rootLength}`, root);
          this.header = h;
          return h;
        })();
        this._h.catch(() => { this._h = null; });
      }
      return this._h;
    }
    async dir(offset, length, h, signal) {
      const key = `${offset}:${length}`;
      if (this.dirs.has(key)) { const d = this.dirs.get(key); this.dirs.delete(key); this.dirs.set(key, d); return d; }
      if (this.pending.has(key)) return this.pending.get(key);
      const p = (async () => {
        const d = parseDirectory(await decompress(await this.bytes(offset, length, signal), h.internalCompression));
        this.dirs.set(key, d);
        while (this.dirs.size > 64) this.dirs.delete(this.dirs.keys().next().value);
        return d;
      })();
      this.pending.set(key, p);
      try { return await p; } finally { this.pending.delete(key); }
    }
    async tile(z, x, y, signal) {
      const h = await this.getHeader();
      if (z < h.minZoom || z > h.maxZoom) return null;
      const id = zxyToTileId(z, x, y);
      let off = h.rootOffset, len = h.rootLength;
      for (let depth = 0; depth <= 3; depth++) {
        const d = await this.dir(off, len, h, signal);
        const e = findTile(d, id);
        if (!e) return null;
        if (e.runLength > 0) return decompress(await this.bytes(h.dataOffset + e.offset, e.length, signal), h.tileCompression);
        off = h.leafOffset + e.offset; len = e.length;
      }
      throw new Error('PMTiles directory too deep');
    }
  }

  const archives = new Map();
  function archive(url) { if (!archives.has(url)) archives.set(url, new Archive(url)); return archives.get(url); }

  /* MapLibre GL JS v4+/v5 protocol handler */
  async function protocol(params, abortController) {
    const signal = abortController && abortController.signal;
    if (params.type === 'json') {
      const url = params.url.slice('pmtiles://'.length);
      const h = await archive(url).getHeader();
      return { data: { tiles: [`${params.url}/{z}/{x}/{y}`], minzoom: h.minZoom, maxzoom: h.maxZoom, bounds: [h.minLon, h.minLat, h.maxLon, h.maxLat] } };
    }
    const m = params.url.match(/^pmtiles:\/\/(.+)\/(\d+)\/(\d+)\/(\d+)$/);
    if (!m) throw new Error('bad pmtiles URL');
    const buf = await archive(m[1]).tile(+m[2], +m[3], +m[4], signal);
    return { data: buf ? new Uint8Array(buf) : new Uint8Array() };
  }

  window.PMTiles = { protocol, zxyToTileId, parseHeader, parseDirectory, findTile, Archive };
})();
