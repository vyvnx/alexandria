import { describe, expect, it } from "vitest";

import { countGraph, defaultMask, toggleEdgeType, toggleKind } from "./filters";
import type { GraphResponse } from "./types";

describe("filter mask", () => {
  it("defaults to everything visible", () => {
    const m = defaultMask();
    expect(m.kinds.source).toBe(true);
    expect(m.edgeTypes["similar-to"]).toBe(true);
  });

  it("toggles a kind immutably", () => {
    const m = defaultMask();
    const next = toggleKind(m, "concept");
    expect(next.kinds.concept).toBe(false);
    expect(m.kinds.concept).toBe(true); // original untouched
  });

  it("toggles an edge type immutably", () => {
    const m = defaultMask();
    const next = toggleEdgeType(m, "uses");
    expect(next.edgeTypes.uses).toBe(false);
    expect(m.edgeTypes.uses).toBe(true);
  });
});

describe("countGraph", () => {
  it("tallies nodes by kind and edges by type", () => {
    const data: GraphResponse = {
      nodes: [
        { id: 1, kind: "source", name: "s", data: {} },
        { id: 2, kind: "entity", name: "e", data: {} },
        { id: 3, kind: "entity", name: "e2", data: {} },
      ],
      edges: [
        { src: 1, dst: 2, type: "mentions", weight: null },
        { src: 2, dst: 3, type: "similar-to", weight: 0.7 },
      ],
    };
    const c = countGraph(data);
    expect(c.nodes).toBe(3);
    expect(c.kinds.entity).toBe(2);
    expect(c.edgeTypes.mentions).toBe(1);
    expect(c.edgeTypes["similar-to"]).toBe(1);
  });
});
