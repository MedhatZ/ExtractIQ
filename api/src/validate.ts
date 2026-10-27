import net from "node:net";
import { z } from "zod";

import { invalidInput, ssrfBlocked } from "./errors.js";

const extractRequestSchema = z.object({
  url: z.string().trim().min(1, "url is required").max(2048),
});

const BLOCKED_HOSTS = new Set([
  "localhost",
  "metadata.google.internal",
  "metadata.google",
  "instance-data",
]);

const BLOCKED_SUFFIXES = [".localhost", ".local", ".internal", ".lan", ".home"];

function ipv4ToInt(ip: string): number | null {
  const parts = ip.split(".");
  if (parts.length !== 4) {
    return null;
  }
  let value = 0;
  for (const part of parts) {
    if (!/^\d+$/.test(part)) {
      return null;
    }
    const octet = Number(part);
    if (octet < 0 || octet > 255) {
      return null;
    }
    value = (value << 8) + octet;
  }
  return value >>> 0;
}

function inCidr(ip: string, cidr: string): boolean {
  const [base, bitsRaw] = cidr.split("/");
  const bits = Number(bitsRaw);
  const ipInt = ipv4ToInt(ip);
  const baseInt = ipv4ToInt(base);
  if (ipInt === null || baseInt === null || Number.isNaN(bits)) {
    return false;
  }
  const mask = bits === 0 ? 0 : (~0 << (32 - bits)) >>> 0;
  return (ipInt & mask) === (baseInt & mask);
}

export function isBlockedIpv4(ip: string): boolean {
  return (
    inCidr(ip, "0.0.0.0/8") ||
    inCidr(ip, "10.0.0.0/8") ||
    inCidr(ip, "127.0.0.0/8") ||
    inCidr(ip, "169.254.0.0/16") ||
    inCidr(ip, "172.16.0.0/12") ||
    inCidr(ip, "192.168.0.0/16") ||
    inCidr(ip, "100.64.0.0/10") ||
    inCidr(ip, "224.0.0.0/4")
  );
}

export function isBlockedIpv6(ip: string): boolean {
  const normalized = ip.toLowerCase();
  if (normalized === "::" || normalized === "::1") {
    return true;
  }
  if (normalized.startsWith("fe80:") || normalized.startsWith("fc") || normalized.startsWith("fd")) {
    return true;
  }
  if (normalized.startsWith("::ffff:")) {
    const mapped = normalized.slice("::ffff:".length);
    if (net.isIP(mapped) === 4) {
      return isBlockedIpv4(mapped);
    }
  }
  return false;
}

function isBlockedHostname(hostname: string): boolean {
  const host = hostname.replace(/\.$/, "").toLowerCase();
  if (!host || BLOCKED_HOSTS.has(host)) {
    return true;
  }
  return BLOCKED_SUFFIXES.some((suffix) => host.endsWith(suffix));
}

export function validateExtractInput(body: unknown): { url: string } {
  const parsed = extractRequestSchema.safeParse(body);
  if (!parsed.success) {
    throw invalidInput("url is required and must be at most 2048 characters");
  }

  let url: URL;
  try {
    url = new URL(parsed.data.url);
  } catch {
    throw invalidInput("url is not a valid URL");
  }

  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw ssrfBlocked("only http and https URLs are allowed");
  }
  if (url.username || url.password) {
    throw ssrfBlocked("URLs with credentials are not allowed");
  }
  if (!url.hostname) {
    throw invalidInput("url must include a hostname");
  }
  if (isBlockedHostname(url.hostname)) {
    throw ssrfBlocked("hostname is not allowed");
  }

  const ipVersion = net.isIP(url.hostname);
  if (ipVersion === 4 && isBlockedIpv4(url.hostname)) {
    throw ssrfBlocked("IP address is not allowed");
  }
  if (ipVersion === 6 && isBlockedIpv6(url.hostname)) {
    throw ssrfBlocked("IP address is not allowed");
  }

  return { url: url.toString() };
}
