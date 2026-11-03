/** Process-local egress guard for the isolated Next.js development process. */
"use strict";

const net = require("node:net");
const dns = require("node:dns");
const permitted = new Set([
  "127.0.0.1",
  "::1",
  "localhost",
  "::ffff:127.0.0.1",
]);

function check(host) {
  if (host && !permitted.has(host)) {
    throw new Error("controlled_analysis_external_network_disabled");
  }
}

const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...args) {
  const normalized = Array.isArray(args[0]) ? args[0] : args;
  const first = normalized[0];
  if (first && typeof first === "object") {
    check(first.host ?? first.hostname);
  } else if (typeof normalized[1] === "string") {
    check(normalized[1]);
  }
  return connect.apply(this, args);
};

const lookup = dns.lookup;
dns.lookup = function (hostname, ...args) {
  check(hostname);
  return lookup.call(this, hostname, ...args);
};
