// Runs Ionic's own PyConAPI.buildRequestAuthHeaders on made-up requests and prints
// each case with the headers Ionic produced, as one JSON array (#662, D-52).
//
//   node signing.js
//
// The inputs are built the way Ionic's call sites build them: JSON bodies with
// JSON.stringify, lead-capture queries with encodeURIComponent, fetch_products
// queries by plain concatenation. Date.now() is fixed per case. The key and secret
// are made up; nothing here is a real credential.

import { PyConAPI } from './src/app/providers/pycon-api';

type Query = { base: string; params: [string, string][]; encoded: boolean };
type Case = {
  name: string;
  about: string;
  key?: string | null;
  secret?: string | null;
  nowMs?: number;
  method: string;
  path?: string;
  query?: Query;
  payload?: unknown;
};

const KEY = 'test-key-0001';
const SECRET = 's3cr3t';
const NOW_MS = 1747324800000;

// syncScan: '...?' + 'attendee_access_code=' + encodeURIComponent(code) + '&badge_validator=' + ...
// fetchAttendeeProducts: '...?attendee_access_code=' + code + '&category_pk_list=' + ids.join(',') + ...
function withQuery(query: Query): string {
  const value = (v: string) => (query.encoded ? encodeURIComponent(v) : v);
  return query.base + '?' + query.params.map(([name, v]) => name + '=' + value(v)).join('&');
}

const leadCapture = '/2027/api/v1/lead_retrieval/capture/';
const leadParams: [string, string][] = [
  ['attendee_access_code', 'ABC123'],
  ['badge_validator', "v/a+l=i d&ä!*'()~-_."],
  ['sponsor_id', '42'],
];

// door-check.page.ts and t-shirt-redemption.page.ts add 'product-redeem-<id>' keys in
// the order of their entries, after the fixed ones.
const redeem: Record<string, unknown> = {
  attendee_access_code: 'ABC123',
  badge_validator: 'f00d',
  scanned_at: '2027-05-15T16:00:00.000Z',
};
for (const [key, value] of [[7, 1], [3, 2], [12, 1]]) {
  redeem['product-redeem-' + key] = key;
  redeem['product-' + key + '-quantity'] = value;
}

const cases: Case[] = [
  {
    name: 'get-empty-body',
    about: 'A GET with no query and an empty body (fetchPreferences).',
    method: 'GET',
    path: '/2027/api/v1/user/mobile_state/',
  },
  {
    name: 'get-query-encoded',
    about: 'Lead capture (syncScan): every query value goes through encodeURIComponent.',
    method: 'GET',
    query: { base: leadCapture, params: leadParams, encoded: true },
  },
  {
    name: 'get-query-encoded-reordered',
    about: 'The same lead-capture query with its parameters in another order: another signature.',
    method: 'GET',
    query: { base: leadCapture, params: [leadParams[2], leadParams[0], leadParams[1]], encoded: true },
  },
  {
    name: 'get-query-unencoded',
    about: 'fetch_products (fetchAttendeeProducts): values concatenated as they are, the comma kept.',
    method: 'GET',
    query: {
      base: '/2027/api/v1/check_in/fetch_products/',
      params: [
        ['attendee_access_code', 'ABC123'],
        ['category_pk_list', [1, 2].join(',')],
        ['mode', 'redemption_mode'],
      ],
      encoded: false,
    },
  },
  {
    name: 'patch-favorites',
    about: 'patchUserData: a compact JSON body.',
    method: 'PATCH',
    path: '/2027/api/v1/user/mobile_state/',
    payload: { favorites: ['123', 'poster-detail-7'] },
  },
  {
    name: 'post-note-non-ascii',
    about: 'syncNote: non-ASCII text (accents, CJK, an emoji outside the BMP) and a newline, kept as UTF-8.',
    method: 'POST',
    path: '/2027/api/v1/lead_retrieval/ABC123/note/',
    payload: { accessCode: 'ABC123', note: 'Interest: hot\nNotes: café, naïve, 東京 🐍', sponsor_id: '42' },
  },
  {
    name: 'post-escapes',
    about: 'Quotes, backslashes, slashes, a tab, a control character and U+2028 in a JSON body.',
    method: 'POST',
    path: '/2027/api/v1/lead_retrieval/ABC123/note/',
    payload: { accessCode: 'ABC123', note: 'She said "hi" \\ C:\\temp\\ a/b </end>\t\u0001\u2028.' },
  },
  {
    name: 'post-redeem-dynamic-keys',
    about: 'redeemProducts: product-redeem-<id> keys in insertion order (7, 3, 12), numbers unquoted.',
    method: 'POST',
    path: '/2027/api/v1/check_in/redeem_products/',
    payload: redeem,
  },
  {
    name: 'post-mask-violation-force',
    about: 'captureMaskViolation with notes and force: a boolean in the body.',
    method: 'POST',
    path: '/2027/api/v1/mask_violations/capture/',
    payload: { attendee_access_code: 'ABC123', notes: 'Second warning', force: true },
  },
  {
    name: 'round-below-half',
    about: 'Date.now() at x.499 s: Math.round goes down.',
    nowMs: 1747324800499,
    method: 'GET',
    path: '/2027/api/v1/user/mobile_state/',
  },
  {
    name: 'round-half-even',
    about: 'Date.now() at x.500 s with x even: Math.round goes up, where banker\'s rounding goes down.',
    nowMs: 1747324800500,
    method: 'GET',
    path: '/2027/api/v1/user/mobile_state/',
  },
  {
    name: 'round-half-odd',
    about: 'Date.now() at x.500 s with x odd: Math.round goes up, as banker\'s rounding does.',
    nowMs: 1747324801500,
    method: 'GET',
    path: '/2027/api/v1/user/mobile_state/',
  },
  {
    name: 'round-above-half',
    about: 'Date.now() at x.501 s: Math.round goes up.',
    nowMs: 1747324800501,
    method: 'GET',
    path: '/2027/api/v1/user/mobile_state/',
  },
  {
    name: 'null-credentials',
    about: 'Signed out: Storage returns null for key and secret; join() renders null as an empty string.',
    key: null,
    secret: null,
    method: 'GET',
    path: '/2027/api/v1/user/check_features/',
  },
];

async function main(): Promise<void> {
  const out: unknown[] = [];
  for (const c of cases) {
    const key = c.key === undefined ? KEY : c.key;
    const secret = c.secret === undefined ? SECRET : c.secret;
    const nowMs = c.nowMs ?? NOW_MS;
    const values: Record<string, unknown> = { key, secret };
    const storage = { create() {}, get: async (name: string) => values[name] };
    const api = new PyConAPI(null as any, storage as any);

    const path = c.query ? withQuery(c.query) : (c.path as string);
    const body = c.payload === undefined ? '' : JSON.stringify(c.payload);
    Date.now = () => nowMs;
    const headers = await api.buildRequestAuthHeaders(c.method, path, body);

    out.push({
      name: c.name,
      about: c.about,
      key,
      secret,
      now_ms: nowMs,
      method: c.method,
      path,
      ...(c.query ? { query: c.query } : {}),
      ...(c.payload === undefined ? {} : { payload: c.payload }),
      body,
      headers,
    });
  }
  process.stdout.write(JSON.stringify(out));
}

main();
