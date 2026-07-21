import { describe, expect, it } from "vitest";

import { buildGraph, carryPositions, edgeColor, edgeKey, kindColor } from "./graph";
import type { GraphResponse } from "./types";

const sample: GraphResponse = {
  nodes: [
    { id: 1, kind: "source", name: "An Article", data: {} },
    { id: 2, kind: "entity", name: "Vaswani", data: { description: "author" } },
    { id: 3, kind: "concept", name: "attention", data: {} },
  ],
  edges: [
    { src: 1, dst: 2, type: "mentions", weight: null },
    { src: 1, dst: 3, type: "about", weight: null },
    { src: 2, dst: 3, type: "similar-to", weight: 0.8 },
  ],
};

describe("buildGraph", () => {
  it("maps every node and edge into the graphology model", () => {
    const g = buildGraph(sample);
    expect(g.order).toBe(3);
    expect(g.size).toBe(3);
    expect(g.hasNode("1")).toBe(true);
  });

  it("colours nodes by kind from the locked palette", () => {
    const g = buildGraph(sample);
    expect(g.getNodeAttribute("1", "color")).toBe(kindColor("source"));
    expect(g.getNodeAttribute("2", "color")).toBe(kindColor("entity"));
    expect(g.getNodeAttribute("3", "color")).toBe(kindColor("concept"));
  });

  it("drops edges whose endpoints are missing", () => {
    const g = buildGraph({
      nodes: [{ id: 1, kind: "concept", name: "lonely", data: {} }],
      edges: [{ src: 1, dst: 99, type: "uses", weight: null }],
    });
    expect(g.size).toBe(0);
  });

  it("dedupes a repeated edge of the same type", () => {
    const g = buildGraph({
      nodes: [
        { id: 1, kind: "concept", name: "a", data: {} },
        { id: 2, kind: "concept", name: "b", data: {} },
      ],
      edges: [
        { src: 1, dst: 2, type: "uses", weight: null },
        { src: 1, dst: 2, type: "uses", weight: null },
      ],
    });
    expect(g.size).toBe(1);
  });
});

describe("sizeByWeight (revisit-weight)", () => {
  // A: 3 sources mention it (weight 3). B: 1 source (weight 1).
  // C: 1 source (weight 1) but FOUR similar-to edges — high degree, low revisit.
  const weighted: GraphResponse = {
    nodes: [
      { id: 1, kind: "source", name: "s1", data: {} },
      { id: 2, kind: "source", name: "s2", data: {} },
      { id: 3, kind: "source", name: "s3", data: {} },
      { id: 10, kind: "concept", name: "A", data: {} },
      { id: 11, kind: "concept", name: "B", data: {} },
      { id: 12, kind: "concept", name: "C", data: {} },
      { id: 13, kind: "concept", name: "D", data: {} },
      { id: 14, kind: "concept", name: "E", data: {} },
    ],
    edges: [
      { src: 1, dst: 10, type: "about", weight: null },
      { src: 2, dst: 10, type: "mentions", weight: null },
      { src: 3, dst: 10, type: "mentions", weight: null },
      { src: 1, dst: 11, type: "mentions", weight: null },
      { src: 1, dst: 12, type: "mentions", weight: null },
      { src: 12, dst: 10, type: "similar-to", weight: 0.9 },
      { src: 12, dst: 11, type: "similar-to", weight: 0.9 },
      { src: 12, dst: 13, type: "similar-to", weight: 0.9 },
      { src: 12, dst: 14, type: "similar-to", weight: 0.9 },
    ],
  };

  it("stores revisit-weight as a node attribute", () => {
    const g = buildGraph(weighted);
    expect(g.getNodeAttribute("10", "weight")).toBe(3);
    expect(g.getNodeAttribute("11", "weight")).toBe(1);
    expect(g.getNodeAttribute("12", "weight")).toBe(1);
  });

  it("makes a topic mentioned by 3 sources larger than a one-off", () => {
    const g = buildGraph(weighted);
    const a = g.getNodeAttribute("10", "size") as number;
    const b = g.getNodeAttribute("11", "size") as number;
    expect(a).toBeGreaterThan(b);
  });

  it("does NOT inflate a high-similar-to / low-mention node", () => {
    const g = buildGraph(weighted);
    // C has higher degree than A (5 vs 3) but is sized like the one-off B.
    expect(g.degree("12")).toBeGreaterThan(g.degree("10"));
    const a = g.getNodeAttribute("10", "size") as number;
    const b = g.getNodeAttribute("11", "size") as number;
    const c = g.getNodeAttribute("12", "size") as number;
    expect(c).toBe(b); // same revisit-weight ⇒ same size
    expect(c).toBeLessThan(a);
  });

  it("pins source nodes to star_size_min", () => {
    const g = buildGraph(weighted);
    expect(g.getNodeAttribute("1", "size")).toBe(4);
    expect(g.getNodeAttribute("2", "size")).toBe(4);
  });

  it("doesn't divide by zero on a graph with no mentions/about", () => {
    const g = buildGraph({
      nodes: [{ id: 1, kind: "concept", name: "x", data: {} }],
      edges: [],
    });
    const size = g.getNodeAttribute("1", "size") as number;
    expect(Number.isFinite(size)).toBe(true);
    expect(size).toBe(4); // floor, no NaN
  });

  it("widens the spread with a custom config range", () => {
    const dflt = buildGraph(weighted);
    const wide = buildGraph(weighted, { star_size_min: 2, star_size_max: 20 });
    const spread = (g: ReturnType<typeof buildGraph>) =>
      (g.getNodeAttribute("10", "size") as number) - (g.getNodeAttribute("11", "size") as number);
    expect(spread(wide)).toBeGreaterThan(spread(dflt));
  });
});

describe("positions (server-side positions spec)", () => {
  it("uses server x/y when present and flags the node placed", () => {
    const g = buildGraph({
      nodes: [
        { id: 1, kind: "concept", name: "settled", data: {}, x: 12.5, y: -3 },
        { id: 2, kind: "concept", name: "unplaced", data: {} },
      ],
      edges: [],
    });
    expect(g.getNodeAttribute("1", "x")).toBe(12.5);
    expect(g.getNodeAttribute("1", "y")).toBe(-3);
    expect(g.getNodeAttribute("1", "placed")).toBe(true);
    expect(g.getNodeAttribute("2", "placed")).toBe(false);
  });

  it("carries settled positions over and marks them placed; new nodes keep seeds", () => {
    const prev = buildGraph(sample);
    prev.setNodeAttribute("2", "x", 42);
    prev.setNodeAttribute("2", "y", -7);

    // node 3 dropped, node 4 added — indices shift, seeds move
    const next = buildGraph({
      nodes: [
        { id: 1, kind: "source", name: "An Article", data: {} },
        { id: 2, kind: "entity", name: "Vaswani", data: {} },
        { id: 4, kind: "concept", name: "transformers", data: {} },
      ],
      edges: [],
    });
    const seeded = {
      x: next.getNodeAttribute("4", "x"),
      y: next.getNodeAttribute("4", "y"),
    };
    carryPositions(prev, next);

    expect(next.getNodeAttribute("2", "x")).toBe(42);
    expect(next.getNodeAttribute("2", "y")).toBe(-7);
    expect(next.getNodeAttribute("2", "placed")).toBe(true);
    expect(next.getNodeAttribute("4", "x")).toBe(seeded.x);
    expect(next.getNodeAttribute("4", "y")).toBe(seeded.y);
    expect(next.getNodeAttribute("4", "placed")).toBe(false);
  });
});

describe("colour + key helpers", () => {
  it("uses rose for semantic edges and brass for typed ones", () => {
    expect(edgeColor("similar-to")).toBe("#e0897c");
    expect(edgeColor("uses")).toBe("#cba34c");
  });

  it("builds a deterministic edge key", () => {
    expect(edgeKey(1, 2, "uses")).toBe("1-2-uses");
  });
});
