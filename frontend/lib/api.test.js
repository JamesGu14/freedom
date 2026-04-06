import test, { afterEach, beforeEach } from "node:test";
import assert from "node:assert/strict";

import { apiFetch, clearSession, getRefreshToken, getToken, migrateLegacySession, resetAuthStateForTests, setToken } from "./api.js";

class MemoryStorage {
  constructor() {
    this.data = new Map();
  }

  getItem(key) {
    return this.data.has(key) ? this.data.get(key) : null;
  }

  setItem(key, value) {
    this.data.set(key, String(value));
  }

  removeItem(key) {
    this.data.delete(key);
  }
}

let storage;
let locationState;

beforeEach(() => {
  storage = new MemoryStorage();
  locationState = { href: "" };
  Object.assign(globalThis, {
    window: {
      localStorage: storage,
      location: locationState,
      dispatchEvent: () => {},
    },
    localStorage: storage,
    Event,
  });
  resetAuthStateForTests();
  clearSession();
});

afterEach(() => {
  resetAuthStateForTests();
  delete globalThis.window;
  delete globalThis.localStorage;
  delete globalThis.fetch;
});

test("setToken persists the token pair", () => {
  setToken("access-1", "refresh-1");

  assert.equal(getToken(), "access-1");
  assert.equal(getRefreshToken(), "refresh-1");
});

test("migrateLegacySession clears stale access-token-only state", () => {
  storage.setItem("access_token", "legacy-access");

  migrateLegacySession();

  assert.equal(storage.getItem("access_token"), null);
  assert.equal(storage.getItem("refresh_token"), null);
});

test("401 triggers refresh and retries the original request", async () => {
  setToken("access-1", "refresh-1");
  const calls = [];

  globalThis.fetch = async (input, init = {}) => {
    const url = String(input);
    const auth = new Headers(init.headers).get("Authorization");
    calls.push({ url, auth });
    if (url.endsWith("/positions")) {
      const firstPositionsCall = calls.filter((entry) => entry.url.endsWith("/positions")).length === 1;
      if (firstPositionsCall) {
        return new Response(JSON.stringify({ detail: "expired" }), { status: 401 });
      }
      assert.equal(auth, "Bearer access-2");
      return new Response(JSON.stringify({ items: [] }), { status: 200 });
    }
    if (url.endsWith("/auth/refresh")) {
      return new Response(JSON.stringify({ access_token: "access-2", refresh_token: "refresh-2" }), { status: 200 });
    }
    throw new Error(`unexpected url ${url}`);
  };

  const response = await apiFetch("/positions");

  assert.equal(response.status, 200);
  assert.equal(getToken(), "access-2");
  assert.equal(getRefreshToken(), "refresh-2");
  assert.equal(locationState.href, "");
});

test("refresh failure clears session and redirects to login", async () => {
  setToken("access-1", "refresh-1");

  globalThis.fetch = async (input) => {
    const url = String(input);
    if (url.endsWith("/positions") || url.endsWith("/auth/refresh")) {
      return new Response(JSON.stringify({ detail: "unauthorized" }), { status: 401 });
    }
    throw new Error(`unexpected url ${url}`);
  };

  await apiFetch("/positions");
  assert.equal(getToken(), null);
  assert.equal(getRefreshToken(), null);
  assert.equal(locationState.href, "/freedom/login");
});
