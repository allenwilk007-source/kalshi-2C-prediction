// In-browser port of the Carbon Trading class model (model.py) plus a light Monte Carlo for
// KXWARMING-50. Same equations, same inputs (data/hw5_inputs.json), same order of operations, so
// the deterministic path matches Python to rounding error. Used by the "What if?" section.
(function () {
  const YEAR0 = 1750, YEAR_END = 2100, T0 = 1850, NFUT = 80;
  const FRAC = [0.13, 0.20, 0.32, 0.25, 0.10];
  const LIFE = [Infinity, 363, 74, 17, 2];
  const MTC_TO_PPM = 0.00047, C0 = 275, FCOEF = 5.35;
  const REG = ["rich", "middle", "poor"];

  const DEFAULTS = {
    g: [0.012, 0.04, 0.022], ei: [-0.0148, -0.0203, -0.0156], ci: [0.0014, 0.0045, -0.0051],
    p1: 0.0256, p2: 1.15, p3: 0.00738, p4: 0.00568, fill: 0, future: null,
  };

  let INP = null, CTX = null;

  function setup(inputs, ctx) { INP = inputs; CTX = ctx; }

  function kayaEmissions(p) {
    const b = INP.base_2020, out = new Float64Array(NFUT);
    for (let k = 1; k <= NFUT; k++) {
      let tot = 0;
      for (let r = 0; r < 3; r++) {
        const R = REG[r];
        const gpc = b.gdp_per_capita[R] * Math.pow(1 + p.g[r], k);
        const ei = b.energy_intensity[R] * Math.pow(1 + p.ei[r], k);
        const ci = b.emissions_intensity[R] * Math.pow(1 + p.ci[r], k);
        tot += INP.population_millions[R][k - 1] * gpc * ei * ci * 1e-9;   // Gt CO2
      }
      out[k - 1] = tot * (12 / 44) * 1000;                                 // Mt C
    }
    return out;
  }

  function run(params) {
    const p = Object.assign({}, DEFAULTS, params || {});
    const hist = INP.hist_emissions_mtc;
    const fut = p.future ? Float64Array.from(p.future) : kayaEmissions(p);
    const T = hist.length + NFUT;
    const E = new Float64Array(T);
    for (let i = 0; i < hist.length; i++) E[i] = hist[i];
    for (let i = 0; i < NFUT; i++) E[hist.length + i] = fut[i] + (p.fill || 0);
    // 5-box carbon cycle
    const decay = LIFE.map(l => Math.exp(-1 / l));
    const box = [C0, 0, 0, 0, 0];
    const ppm = new Float64Array(T), F = new Float64Array(T);
    ppm[0] = box.reduce((a, c) => a + c, 0);
    for (let t = 1; t < T; t++) {
      for (let j = 0; j < 5; j++) box[j] = decay[j] * box[j] + E[t] * FRAC[j] * MTC_TO_PPM;
      ppm[t] = box[0] + box[1] + box[2] + box[3] + box[4];
    }
    for (let t = 0; t < T; t++) F[t] = FCOEF * Math.log(ppm[t] / C0);
    // two-box temperature from 1850
    const AT = new Float64Array(T).fill(NaN);
    const i0 = T0 - YEAR0;
    let at = 0, ot = 0;
    AT[i0] = 0;
    for (let t = i0 + 1; t < T; t++) {
      const atNew = at + p.p1 * (p.p2 * F[t] - at) + p.p3 * (ot - at);
      ot = ot + p.p4 * (at - ot);
      at = atNew;
      AT[t] = at;
    }
    let base = 0;
    for (let y = 1850; y <= 1900; y++) base += AT[y - YEAR0];
    base /= 51;
    const Trb = AT.map(v => v - base);
    return { years: Array.from({ length: T }, (_, i) => YEAR0 + i), E, ppm, F, T: Trb, raw: AT, params: p };
  }

  // deterministic RNG so sliders move smoothly instead of jittering
  function rng(seed) {
    let a = seed >>> 0;
    const u = () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    let spare = null;
    const n = () => { if (spare !== null) { const s = spare; spare = null; return s; }
      let x, y, r; do { x = 2 * u() - 1; y = 2 * u() - 1; r = x * x + y * y; } while (r === 0 || r >= 1);
      const m = Math.sqrt(-2 * Math.log(r) / r); spare = y * m; return x * m; };
    return n;
  }

  const round2 = x => Math.floor(x * 100 + 0.5 + 1e-9) / 100;

  // Monte Carlo for KXWARMING-50 from the 2026 nowcast state (anchored, AR(1) noise, 2-of-4 rule)
  function probability(res, opts) {
    const o = Object.assign({ n: 4000, seed: 12345, lastYear: 2049 }, opts || {});
    const T = res.T, c = CTX, N = o.n, randn = rng(o.seed);
    let b = 0;
    c.anchor_years.forEach((y, i) => { b += c.anchor_signal[i] - T[y - YEAR0]; });
    b /= c.anchor_years.length;
    const phi = c.ar1.phi, sig = c.ar1.sigma, cc = b * (1 - phi);
    const years = []; for (let y = 2027; y <= o.lastYear; y++) years.push(y);
    const Y = years.length;
    const d = c.offsets, K = d.delta.length;
    const stat = Array.from({ length: Y }, () => new Float64Array(N));
    const sig2049 = new Float64Array(N);
    const first = new Float64Array(N).fill(NaN);
    let yes = 0;
    const u = new Float64Array(K);
    const innov = d.rho.map((rho, k) => d.tau[k] * Math.sqrt(Math.max(0, 1 - rho * rho)));
    for (let i = 0; i < N; i++) {
      const s26 = c.signal_2026.mean + c.signal_2026.sd * randn();
      const r0 = s26 - T[2026 - YEAR0];
      let r = cc + phi * r0 + sig * randn();
      if (c.momentum.used) r += (c.momentum.phi1 - phi) * (r0 - b) + c.momentum.phi2 * c.q4_minus_annual_2026;
      for (let k = 0; k < K; k++) u[k] = d.last_dev[k];
      let hit = false;
      for (let t = 0; t < Y; t++) {
        if (t > 0) r = cc + phi * r + sig * randn();
        const S = T[years[t] - YEAR0] + r;
        let top = -Infinity, second = -Infinity;          // second-highest of the four datasets
        for (let k = 0; k < K; k++) {
          if (d.rho[k] > 0.3) u[k] = d.rho[k] * u[k] + innov[k] * randn();
          else u[k] = d.tau[k] * randn();
          const v = round2(S + d.delta[k] + u[k]);
          if (v > top) { second = top; top = v; } else if (v > second) second = v;
        }
        stat[t][i] = second;
        if (!hit && second >= 2.0 - 1e-9) { hit = true; first[i] = years[t]; }
        if (t === Y - 1) sig2049[i] = S;
      }
      if (hit) yes++;
    }
    const q = (arr, p) => { const a = arr.filter(v => !isNaN(v)).sort();   // typed-array sort is numeric
      return a.length ? a[Math.min(a.length - 1, Math.floor(p * a.length))] : NaN; };
    const fan = stat.map(col => { const s = col.slice().sort();
      return [0.05, 0.25, 0.5, 0.75, 0.95].map(p => s[Math.min(N - 1, Math.floor(p * N))]); });
    return { pYes: yes / N, b, years, fan, firstMedian: q(first, 0.5), firstP10: q(first, 0.1),
             firstP90: q(first, 0.9), n: N };
  }

  function check() {
    const ref = CTX.reference.template_temp_1750_2100;
    const r = run({});
    let maxDiff = 0;
    ref.forEach((v, i) => { if (v !== null && !isNaN(r.T[i])) maxDiff = Math.max(maxDiff, Math.abs(r.T[i] - v)); });
    return { maxAbsDiffT: maxDiff, pRef: CTX.reference.template_p_yes, pJs: probability(r, { n: 20000 }).pYes };
  }

  window.ClassModel = { setup, run, probability, check, DEFAULTS, ecs: p2 => p2 * FCOEF * Math.log(2), YEAR0 };
})();
