import { describe, expect, it } from "vitest";

import { centroid, convexHull, padHull, type Point } from "./hull";

const has = (hull: Point[], p: Point) => hull.some((q) => q.x === p.x && q.y === p.y);

describe("convexHull", () => {
  it("returns the 4 corners of a square, dropping an interior point", () => {
    const corners = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
    ];
    const hull = convexHull([...corners, { x: 5, y: 5 }]);
    expect(hull).not.toBeNull();
    expect(hull).toHaveLength(4);
    for (const c of corners) expect(has(hull!, c)).toBe(true);
    expect(has(hull!, { x: 5, y: 5 })).toBe(false); // interior dropped
  });

  it("drops edge-collinear points, keeping only true corners", () => {
    const hull = convexHull([
      { x: 0, y: 0 },
      { x: 5, y: 0 }, // on the bottom edge
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
    ]);
    expect(hull).toHaveLength(4);
    expect(has(hull!, { x: 5, y: 0 })).toBe(false);
  });

  it("returns null for a degenerate (all-collinear) set", () => {
    expect(
      convexHull([
        { x: 0, y: 0 },
        { x: 1, y: 1 },
        { x: 2, y: 2 },
      ]),
    ).toBeNull();
  });

  it("returns null for 1 or 2 points (caller draws a circle)", () => {
    expect(convexHull([{ x: 0, y: 0 }])).toBeNull();
    expect(convexHull([{ x: 0, y: 0 }, { x: 1, y: 1 }])).toBeNull();
  });
});

describe("centroid + padHull", () => {
  it("averages the points", () => {
    const c = centroid([
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
    ]);
    expect(c).toEqual({ x: 5, y: 5 });
  });

  it("pushes every vertex farther from the centre", () => {
    const square = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
    ];
    const c = centroid(square);
    const padded = padHull(square, c, 4);
    for (let i = 0; i < square.length; i++) {
      const before = Math.hypot(square[i].x - c.x, square[i].y - c.y);
      const after = Math.hypot(padded[i].x - c.x, padded[i].y - c.y);
      expect(after).toBeGreaterThan(before);
      expect(after - before).toBeCloseTo(4, 5); // pushed out by exactly px
    }
  });
});
