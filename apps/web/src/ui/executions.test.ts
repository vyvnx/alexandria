import { describe, expect, it } from "vitest";

import { fmtCost, fmtDuration, fmtTokens } from "./executions";

describe("fmtCost", () => {
  it("em-dashes missing cost (unpriced / local model)", () => {
    expect(fmtCost(null)).toBe("—");
  });
  it("shows sub-cent costs with 4 decimals", () => {
    expect(fmtCost(0.001234)).toBe("$0.0012");
  });
  it("shows regular costs with 2 decimals", () => {
    expect(fmtCost(1.5)).toBe("$1.50");
  });
});

describe("fmtDuration", () => {
  it("em-dashes a still-running execution", () => {
    expect(fmtDuration(null)).toBe("—");
  });
  it("keeps sub-second in ms", () => {
    expect(fmtDuration(850)).toBe("850ms");
  });
  it("shows seconds with one decimal", () => {
    expect(fmtDuration(1234)).toBe("1.2s");
  });
});

describe("fmtTokens", () => {
  it("em-dashes when no usage was reported", () => {
    expect(fmtTokens(0, 0)).toBe("—");
    expect(fmtTokens(null, null)).toBe("—");
  });
  it("abbreviates thousands and shows in → out", () => {
    expect(fmtTokens(1234, 340)).toBe("1.2k → 340");
  });
});
