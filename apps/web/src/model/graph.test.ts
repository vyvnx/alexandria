import { describe, expect, it } from "vitest";

import { buildGraph, edgeColor, edgeKey, kindColor } from "./graph";
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

  it("sizes stars by degree (the hub is larger than a leaf)", () => {
    // A star graph makes the hub unambiguous: centre has degree 2, leaves 1.
    const star = buildGraph({
      nodes: [
        { id: 1, kind: "concept", name: "hub", data: {} },
        { id: 2, kind: "concept", name: "a", data: {} },
        { id: 3, kind: "concept", name: "b", data: {} },
      ],
      edges: [
        { src: 1, dst: 2, type: "uses", weight: null },
        { src: 1, dst: 3, type: "uses", weight: null },
      ],
    });
    const hub = star.getNodeAttribute("1", "size") as number;
    const leaf = star.getNodeAttribute("2", "size") as number;
    expect(hub).toBeGreaterThan(leaf);
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

describe("colour + key helpers", () => {
  it("uses rose for semantic edges and brass for typed ones", () => {
    expect(edgeColor("similar-to")).toBe("#e0897c");
    expect(edgeColor("uses")).toBe("#cba34c");
  });

  it("builds a deterministic edge key", () => {
    expect(edgeKey(1, 2, "uses")).toBe("1-2-uses");
  });
});
