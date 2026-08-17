import { describe, expect, it } from "vitest";

import {
  classifyCrawlError,
  classifyCrawlErrors,
  groupCrawlErrors,
  retryabilityLabel,
} from "@/lib/crawl-errors";

describe("classifyCrawlError", () => {
  it("classifies a TLS verification failure with a human title and host", () => {
    const result = classifyCrawlError({
      error: "SSLCertVerificationError: certificate verify failed: unable to get local issuer certificate",
      error_type: "SSLCertVerificationError",
      source: "GERC",
      source_page: "Draft Regulations",
      url: "https://gercin.org/orders",
      attempt: 3,
      max_attempts: 3,
    });

    expect(result.category).toBe("tls");
    expect(result.title).toBe("Secure connection could not be verified");
    expect(result.host).toBe("gercin.org");
    expect(result.explanation).toContain("gercin.org");
    expect(result.retryability).toBe("not_retryable");
    expect(result.facts).toEqual(
      expect.arrayContaining([
        { label: "Host", value: "gercin.org" },
        { label: "Attempt", value: "3 of 3" },
        { label: "Page", value: "Draft Regulations" },
      ]),
    );
  });

  it("prefers structured tls_reason from the pipeline payload", () => {
    const result = classifyCrawlError({
      error:
        "TLS certificate verification failed: unable to get local issuer certificate",
      error_type: "tls_certificate_error",
      tls_reason: "unable_to_get_local_issuer",
      cause_type: "ConnectError",
      error_message:
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate",
      url: "https://gercin.org/orders/tariff_orders",
      source: "GERC",
    });

    expect(result.category).toBe("tls");
    expect(result.title).toBe(
      "TLS certificate verification failed: unable to get local issuer certificate",
    );
    expect(result.explanation).toContain("unable to get local issuer certificate");
    expect(result.explanation.toLowerCase()).not.toContain("verify=false");
    expect(result.facts).toEqual(
      expect.arrayContaining([
        { label: "Error type", value: "tls_certificate_error" },
        {
          label: "TLS reason",
          value: "unable to get local issuer certificate",
        },
        { label: "Underlying error", value: "ConnectError" },
      ]),
    );
  });

  it("surfaces self-signed-in-chain reason for DERC-style failures", () => {
    const result = classifyCrawlError({
      error:
        "TLS certificate verification failed: self-signed certificate in certificate chain",
      error_type: "tls_certificate_error",
      tls_reason: "self_signed_certificate_in_chain",
      cause_type: "ConnectError",
      url: "https://www.derc.gov.in/notices/press-release",
    });

    expect(result.category).toBe("tls");
    expect(result.title).toContain("self-signed certificate in certificate chain");
    expect(result.host).toBe("www.derc.gov.in");
  });

  it("never suggests weakening TLS verification", () => {
    const result = classifyCrawlError({
      error: "certificate verify failed",
      error_type: "SSLError",
    });

    const copy = `${result.title} ${result.explanation}`.toLowerCase();
    expect(copy).not.toContain("verify=false");
    expect(copy).not.toContain("disable");
    expect(copy).not.toContain("skip verification");
    expect(copy).not.toContain("insecure");
  });

  it("classifies DNS resolution failures as retryable", () => {
    const result = classifyCrawlError({
      error: "getaddrinfo failed: Name or service not known",
      error_type: "gaierror",
      host: "example.gov.in",
    });

    expect(result.category).toBe("dns");
    expect(result.retryability).toBe("retryable");
  });

  it("separates HTTP 4xx from HTTP 5xx", () => {
    const notFound = classifyCrawlError({
      error: "Request failed",
      status_code: 404,
      url: "https://cerc.gov.in/orders",
    });
    expect(notFound.category).toBe("http_client");
    expect(notFound.httpStatus).toBe(404);
    expect(notFound.explanation).toContain("moved");
    expect(notFound.retryability).toBe("needs_configuration");

    const serverError = classifyCrawlError({
      error: "Bad gateway",
      status_code: 502,
      url: "https://cerc.gov.in/orders",
    });
    expect(serverError.category).toBe("http_server");
    expect(serverError.retryability).toBe("retryable");
  });

  it("recognises rate limiting", () => {
    const result = classifyCrawlError({ error: "rejected", status: 429 });

    expect(result.category).toBe("http_client");
    expect(result.explanation).toContain("rate limited");
  });

  it("classifies timeouts", () => {
    const result = classifyCrawlError({
      error: "HTTPSConnectionPool: Read timed out. (read timeout=30)",
      error_type: "ReadTimeout",
    });

    expect(result.category).toBe("timeout");
    expect(result.retryability).toBe("retryable");
  });

  it("classifies an empty page selection as a configuration issue", () => {
    const result = classifyCrawlError({
      error: "No enabled source pages are crawlable for source GERC",
      source: "GERC",
      configured_pages: 3,
      enabled_pages: 0,
      crawlable_pages: 0,
      reason: "all_pages_disabled",
    });

    expect(result.category).toBe("configuration");
    expect(result.retryability).toBe("needs_configuration");
    expect(result.facts).toEqual(
      expect.arrayContaining([
        { label: "Configured pages", value: "3" },
        { label: "Enabled pages", value: "0" },
        { label: "Crawlable pages", value: "0" },
      ]),
    );
  });

  it("classifies parser and validation failures", () => {
    expect(
      classifyCrawlError({ error: "Failed to parse PDF content" }).category,
    ).toBe("parser");
    expect(
      classifyCrawlError({ error: "ValidationError: title is a required field" })
        .category,
    ).toBe("validation");
  });

  it("falls back to unknown while preserving the raw payload", () => {
    const raw = { error: "something entirely unexpected happened", extra: 1 };
    const result = classifyCrawlError(raw);

    expect(result.category).toBe("unknown");
    expect(result.title).toContain("something entirely unexpected");
    expect(result.raw).toBe(raw);
  });

  it("handles an empty payload without throwing", () => {
    const result = classifyCrawlError({});

    expect(result.category).toBe("unknown");
    expect(result.title).toBe("The crawler reported an unclassified failure");
  });
});

describe("classifyCrawlErrors", () => {
  it("tolerates missing and non-array input", () => {
    expect(classifyCrawlErrors(undefined)).toEqual([]);
    expect(classifyCrawlErrors(null)).toEqual([]);
  });
});

describe("groupCrawlErrors", () => {
  it("collapses identical failures across pages", () => {
    const errors = classifyCrawlErrors([
      { error: "certificate verify failed", source_page: "Orders" },
      { error: "certificate verify failed", source_page: "Draft Regulations" },
      { error: "Read timed out", error_type: "ReadTimeout" },
    ]);

    const groups = groupCrawlErrors(errors);

    expect(groups).toHaveLength(2);
    expect(groups[0].items).toHaveLength(2);
    expect(groups[1].category).toBe("timeout");
  });
});

describe("retryabilityLabel", () => {
  it("renders operator-facing wording", () => {
    expect(retryabilityLabel("retryable")).toBe("Safe to retry");
    expect(retryabilityLabel("not_retryable")).toBe("Retrying will not help");
    expect(retryabilityLabel("needs_configuration")).toBe(
      "Needs configuration change",
    );
  });
});
