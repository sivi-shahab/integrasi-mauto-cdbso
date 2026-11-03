// Stress test k6 untuk POST /v1/report_mauto
//
// Contoh menjalankan:
//   k6 run tests/k6/report_mauto_stress.js \
//     -e BASE_URL=http://localhost:8013 \
//     -e API_KEY_NAME=X-API-KEY -e API_KEY=xxxx \
//     -e SCENARIO=stress \
//     -e DATA_FILE=./data.csv
//
// SCENARIO: smoke | load | stress | spike | soak   (default: stress)
// DATA_FILE (opsional): CSV dengan header nik,apply_date[,cc_reff,branch_code,account_number]
//   apply_date format ddmmyyyy. Path relatif terhadap file script ini.
//   Jika tidak diisi, dipakai NIK/APPLY_DATE dari env.
// RESULT_DIR (opsional, default: tests/k6/results): folder output handleSummary,
//   relatif terhadap direktori tempat k6 dijalankan. Folder harus sudah ada.

import http from 'k6/http';
import { check } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter, Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8013';
const API_KEY_NAME = __ENV.API_KEY_NAME || 'X-API-KEY';
const API_KEY = __ENV.API_KEY || '';
const SCENARIO = __ENV.SCENARIO || 'stress';
const LIMIT = parseInt(__ENV.LIMIT || '100', 10);
const RESULT_DIR = (__ENV.RESULT_DIR || 'tests/k6/results').replace(/\/+$/, '');

const ENDPOINT = `${BASE_URL}/v1/report_mauto`;

// ---------- Test data ----------
const testData = new SharedArray('report_mauto_data', () => {
  if (__ENV.DATA_FILE) {
    const lines = open(__ENV.DATA_FILE).split(/\r?\n/).filter((l) => l.trim() !== '');
    const header = lines.shift().split(',').map((h) => h.trim());
    return lines.map((line) => {
      const cols = line.split(',');
      const row = {};
      header.forEach((h, i) => {
        const v = (cols[i] || '').trim();
        if (v !== '') row[h] = v;
      });
      return row;
    });
  }
  return [{
    nik: __ENV.NIK || '3171234567890001',
    apply_date: __ENV.APPLY_DATE || '01012026',
  }];
});

// ---------- Custom metrics ----------
const businessSuccess = new Rate('business_success');      // responseCode == "00"
const rowsReturned = new Trend('rows_returned');
const nonSuccessCodes = new Counter('non_success_response_code');

// ---------- Scenarios ----------
const scenarios = {
  smoke: {
    executor: 'constant-vus',
    vus: 1,
    duration: '30s',
  },
  load: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '1m', target: 20 },
      { duration: '3m', target: 20 },
      { duration: '1m', target: 0 },
    ],
  },
  stress: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '1m', target: 20 },
      { duration: '2m', target: 50 },
      { duration: '2m', target: 100 },
      { duration: '2m', target: 200 },
      { duration: '2m', target: 300 },
      { duration: '2m', target: 0 },   // recovery
    ],
    gracefulRampDown: '30s',
  },
  spike: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '30s', target: 10 },
      { duration: '10s', target: 300 },  // lonjakan tiba-tiba
      { duration: '1m', target: 300 },
      { duration: '10s', target: 10 },
      { duration: '1m', target: 10 },
      { duration: '10s', target: 0 },
    ],
  },
  soak: {
    executor: 'constant-vus',
    vus: 30,
    duration: '30m',
  },
};

if (!scenarios[SCENARIO]) {
  throw new Error(`SCENARIO tidak dikenal: ${SCENARIO}. Pilih: ${Object.keys(scenarios).join(', ')}`);
}

export const options = {
  scenarios: { [SCENARIO]: scenarios[SCENARIO] },
  thresholds: {
    http_req_failed: ['rate<0.01'],                  // < 1% error HTTP
    http_req_duration: ['p(95)<1000', 'p(99)<2000'], // ms
    business_success: ['rate>0.99'],
    checks: ['rate>0.99'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export function setup() {
  if (!API_KEY) {
    console.warn('API_KEY kosong — request kemungkinan besar akan 401.');
  }
  // Sanity check sebelum load dimulai
  const res = http.post(ENDPOINT, JSON.stringify(testData[0]), { headers: buildHeaders() });
  if (res.status !== 200) {
    throw new Error(`Sanity check gagal: status=${res.status} body=${res.body}`);
  }
}

function buildHeaders() {
  return {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    [API_KEY_NAME]: API_KEY,
  };
}

export default function () {
  const row = testData[Math.floor(Math.random() * testData.length)];
  const payload = JSON.stringify({ ...row, limit: LIMIT, offset: 0 });

  const res = http.post(ENDPOINT, payload, {
    headers: buildHeaders(),
    tags: { name: 'POST /v1/report_mauto' },
    timeout: '30s',
  });

  let body = null;
  try {
    body = res.json();
  } catch (_) {
    // body bukan JSON (mis. timeout / 502 dari proxy)
  }

  // Service mengembalikan HTTP 200 juga untuk error bisnis (responseCode 40/91),
  // jadi responseCode harus dicek terpisah dari status HTTP.
  const ok = check(res, {
    'status is 200': (r) => r.status === 200,
    'body is JSON': () => body !== null,
    'responseCode is 00': () => body !== null && body.responseCode === '00',
    'data is array': () => body !== null && Array.isArray(body.data),
  });

  const isSuccess = body !== null && body.responseCode === '00';
  businessSuccess.add(isSuccess);
  if (isSuccess) {
    rowsReturned.add(body.data.length);
  } else {
    nonSuccessCodes.add(1, { code: body ? String(body.responseCode) : `http_${res.status}` });
  }

  // Tanpa sleep → tiap VU menembak secepat mungkin (closed model, cocok untuk stress).
  // Tambahkan sleep(1) jika ingin mensimulasikan think time pengguna.
}

// ---------- Summary ke file ----------
// Menghasilkan 3 output:
//   <RESULT_DIR>/summary_<scenario>_<timestamp>.json  — data lengkap dari k6
//   <RESULT_DIR>/summary_<scenario>_<timestamp>.txt   — ringkasan yang mudah dibaca
//   stdout                                            — ringkasan yang sama dengan .txt
// Formatter ditulis sendiri (tanpa import jslib.k6.io) agar bisa jalan tanpa internet.

const SUMMARY_METRICS = [
  'http_reqs',
  'iterations',
  'http_req_duration',
  'http_req_waiting',
  'http_req_failed',
  'business_success',
  'checks',
  'rows_returned',
  'non_success_response_code',
  'data_received',
  'data_sent',
  'vus_max',
];

function fmtNum(n, digits = 2) {
  return typeof n === 'number' ? n.toFixed(digits) : String(n);
}

function fmtBytes(n) {
  const units = ['B', 'kB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(2)} ${units[i]}`;
}

function fmtMetric(name, metric) {
  const v = metric.values;
  switch (metric.type) {
    case 'trend': {
      const keys = ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'].filter((k) => k in v);
      const unit = metric.contains === 'time' ? 'ms' : '';
      return keys.map((k) => `${k}=${fmtNum(v[k])}${unit}`).join(' ');
    }
    case 'rate':
      return `${fmtNum(v.rate * 100)}% (${v.passes} ✓ / ${v.fails} ✗)`;
    case 'counter':
      return metric.contains === 'data'
        ? `${fmtBytes(v.count)} (${fmtBytes(v.rate)}/s)`
        : `${v.count} (${fmtNum(v.rate)}/s)`;
    case 'gauge':
      return `${v.value} (min=${v.min} max=${v.max})`;
    default:
      return JSON.stringify(v);
  }
}

function collectChecks(group, out = []) {
  (group.checks || []).forEach((c) => out.push(c));
  (group.groups || []).forEach((g) => collectChecks(g, out));
  return out;
}

function buildTextSummary(data, startedAt) {
  const lines = [];
  const durationSec = data.state && data.state.testRunDurationMs
    ? (data.state.testRunDurationMs / 1000).toFixed(1)
    : '-';

  lines.push('='.repeat(70));
  lines.push(' k6 summary — POST /v1/report_mauto');
  lines.push('='.repeat(70));
  lines.push(` Scenario   : ${SCENARIO}`);
  lines.push(` Target     : ${ENDPOINT}`);
  lines.push(` Data rows  : ${testData.length}${__ENV.DATA_FILE ? ` (${__ENV.DATA_FILE})` : ' (env NIK/APPLY_DATE)'}`);
  lines.push(` Limit      : ${LIMIT}`);
  lines.push(` Selesai    : ${startedAt}`);
  lines.push(` Durasi     : ${durationSec}s`);
  lines.push('');

  lines.push('--- Checks ' + '-'.repeat(59));
  collectChecks(data.root_group).forEach((c) => {
    const total = c.passes + c.fails;
    const pct = total ? ((c.passes / total) * 100).toFixed(2) : '0.00';
    lines.push(` ${c.fails === 0 ? '✓' : '✗'} ${c.name.padEnd(22)} ${pct}% (${c.passes} ✓ / ${c.fails} ✗)`);
  });
  lines.push('');

  lines.push('--- Metrics ' + '-'.repeat(58));
  SUMMARY_METRICS.forEach((name) => {
    const metric = data.metrics[name];
    if (metric) lines.push(` ${name.padEnd(28, '.')} ${fmtMetric(name, metric)}`);
  });
  // Rincian non_success_response_code per tag `code` tidak ada di summary; lihat --out json
  lines.push('');

  lines.push('--- Thresholds ' + '-'.repeat(55));
  let allOk = true;
  Object.keys(data.metrics).forEach((name) => {
    const th = data.metrics[name].thresholds;
    if (!th) return;
    Object.keys(th).forEach((expr) => {
      const ok = th[expr].ok;
      if (!ok) allOk = false;
      lines.push(` ${ok ? '✓' : '✗'} ${name} ${expr}`);
    });
  });
  lines.push('');
  lines.push(` HASIL: ${allOk ? 'LULUS — semua threshold terpenuhi' : 'GAGAL — ada threshold yang tidak terpenuhi'}`);
  lines.push('='.repeat(70));

  return lines.join('\n') + '\n';
}

export function handleSummary(data) {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_` +
    `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  const base = `${RESULT_DIR}/summary_${SCENARIO}_${stamp}`;

  const text = buildTextSummary(data, now.toString());
  const meta = {
    scenario: SCENARIO,
    endpoint: ENDPOINT,
    data_file: __ENV.DATA_FILE || null,
    data_rows: testData.length,
    limit: LIMIT,
    finished_at: now.toISOString(),
  };

  return {
    stdout: text + `\nHasil disimpan ke: ${base}.json dan ${base}.txt\n`,
    [`${base}.json`]: JSON.stringify({ meta, ...data }, null, 2),
    [`${base}.txt`]: text,
  };
}
