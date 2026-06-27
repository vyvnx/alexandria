import { describe, expect, it } from "vitest";

import { TRICKLE_CEILING, nextTrickle } from "./trickle";

describe("nextTrickle", () => {
  it("advances upward from a low value", () => {
    expect(nextTrickle(0)).toBeGreaterThan(0);
  });

  it("increases monotonically while creeping", () => {
    let p = 0;
    for (let i = 0; i < 50; i++) {
      const next = nextTrickle(p);
      expect(next).toBeGreaterThan(p);
      p = next;
    }
  });

  it("never reaches or exceeds the ceiling, even after many steps", () => {
    let p = 0;
    for (let i = 0; i < 500; i++) p = nextTrickle(p);
    expect(p).toBeLessThan(TRICKLE_CEILING);
  });

  it("creeps close to the ceiling after enough steps", () => {
    let p = 0;
    for (let i = 0; i < 100; i++) p = nextTrickle(p);
    expect(p).toBeGreaterThan(TRICKLE_CEILING - 1);
  });

  it("stays under the ceiling when handed a value already above it", () => {
    const next = nextTrickle(95);
    expect(next).toBeLessThan(TRICKLE_CEILING);
    expect(next).toBeGreaterThanOrEqual(0);
  });
});
