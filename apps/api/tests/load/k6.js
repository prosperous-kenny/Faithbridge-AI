// Phase 5 load gate for the dashboard surface, for users who have k6
// (https://grafana.com/k6) installed. The gate that actually runs in CI here
// is tests/load/measure.py, which needs no extra binaries; this file is the
// canonical definition of the scenario so the two stay comparable.
//
// Usage:
//   k6 run -e FAITHBRIDGE_BASE=http://127.0.0.1:8000 \
//          -e FAITHBRIDGE_TOKEN=<leader jwt> tests/load/k6.js
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const BASE = __ENV.FAITHBRIDGE_BASE || "http://127.0.0.1:8000";
const TOKEN = __ENV.FAITHBRIDGE_TOKEN || "";
const params = {
  headers: { Authorization: `Bearer ${TOKEN}` },
};

const READ_PATHS = [
  "/api/v1/dashboard/stats",
  "/api/v1/dashboard/community-insights",
  "/api/v1/dashboard/impact-report",
  "/api/v1/dashboard/impact-report/export?format=pdf",
];

const FIVE_NOT_2XX = new Rate("five_(!=2xx)");
const endpointTrend = {};
for (const path of READ_PATHS) {
  endpointTrend[path] = new Trend(path);
}

export const options = {
  scenarios: {
    dashboards: {
      executor: "constant-vus",
      vus: 40,
      duration: "60s",
    },
  },
  thresholds: {
    http_req_duration: ["p(95) < 3000"],
  },
};

export default function () {
  const path = READ_PATHS[__ITER % READ_PATHS.length];
  const res = http.get(`${BASE}${path}`, params);
  FIVE_NOT_2XX.add(res.status >= 500);
  endpointTrend[path].add(res.duration);
  check(res, {
    [`GET ${path} completed`]: (r) => r.status >= 200 && r.status < 500,
  });
  sleep(0.25);
}