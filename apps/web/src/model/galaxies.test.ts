import { describe, expect, it } from "vitest";

import { detectGalaxies, nameGalaxy } from "./galaxies";
import { buildGraph } from "./graph";
import type { GraphResponse } from "./types";

/* Two dense triangles (programming-ish / fighting-ish), each with its own
   source, plus a lone source→concept pair. The clusters share no edges, so
   Louvain must find exactly two communities; the pair is too small to hull. */
const twoClusters: GraphResponse = {
  nodes: [
    { id: 1, kind: "source", name: "ml-paper", data: {} },
    { id: 10, kind: "concept", name: "transformers", data: {} },
    { id: 11, kind: "concept", name: "attention", data: {} },
    { id: 12, kind: "concept", name: "embeddings", data: {} },
    { id: 2, kind: "source", name: "bjj-blog", data: {} },
    { id: 20, kind: "concept", name: "guard", data: {} },
    { id: 21, kind: "concept", name: "sweep", data: {} },
    { id: 22, kind: "concept", name: "submission", data: {} },
    { id: 3, kind: "source", name: "stray-note", data: {} },
    { id: 30, kind: "concept", name: "loner", data: {} },
  ],
  edges: [
    // cluster A: source 1 mentions 10/11/12; concepts form a similar-to triangle
    { src: 1, dst: 10, type: "about", weight: null },
    { src: 1, dst: 11, type: "mentions", weight: null },
    { src: 1, dst: 12, type: "mentions", weight: null },
    { src: 10, dst: 11, type: "similar-to", weight: 0.9 },
    { src: 11, dst: 12, type: "similar-to", weight: 0.9 },
    { src: 10, dst: 12, type: "similar-to", weight: 0.9 },
    // cluster B: source 2 mentions 20/21/22; concepts form a similar-to triangle
    { src: 2, dst: 20, type: "about", weight: null },
    { src: 2, dst: 21, type: "mentions", weight: null },
    { src: 2, dst: 22, type: "mentions", weight: null },
    { src: 20, dst: 21, type: "similar-to", weight: 0.9 },
    { src: 21, dst: 22, type: "similar-to", weight: 0.9 },
    { src: 20, dst: 22, type: "similar-to", weight: 0.9 },
    // lone pair: source 3 mentions a single concept
    { src: 3, dst: 30, type: "mentions", weight: null },
  ],
};

describe("detectGalaxies", () => {
  it("finds two galaxies for two clearly-separated clusters", () => {
    const g = buildGraph(twoClusters);
    const map = detectGalaxies(g);
    expect(map.byId).toHaveLength(2);
  });

  it("leaves a sub-threshold clump un-hulled (a lone star)", () => {
    const g = buildGraph(twoClusters);
    const map = detectGalaxies(g);
    // the 2-node component is not assigned to any galaxy
    expect(map.nodeToGalaxy["30"]).toBeUndefined();
    expect(map.nodeToGalaxy["3"]).toBeUndefined();
    // every surviving galaxy has at least the configured minimum members
    for (const galaxy of map.byId) expect(galaxy.members.length).toBeGreaterThanOrEqual(3);
  });

  it("assigns a distinct palette colour per galaxy", () => {
    const g = buildGraph(twoClusters);
    const colors = detectGalaxies(g).byId.map((x) => x.color);
    expect(new Set(colors).size).toBe(colors.length);
  });

  it("is deterministic — same input yields same ids, colours, and names", () => {
    const a = detectGalaxies(buildGraph(twoClusters));
    const b = detectGalaxies(buildGraph(twoClusters));
    expect(JSON.stringify(a)).toBe(JSON.stringify(b));
  });
});

describe("nameGalaxy", () => {
  // Vaswani (entity) is the most-revisited member; transformers (concept) next.
  const naming: GraphResponse = {
    nodes: [
      { id: 1, kind: "source", name: "s1", data: {} },
      { id: 2, kind: "source", name: "s2", data: {} },
      { id: 3, kind: "source", name: "s3", data: {} },
      { id: 10, kind: "concept", name: "transformers", data: {} }, // weight 2
      { id: 11, kind: "concept", name: "rnn", data: {} }, // weight 1
      { id: 12, kind: "entity", name: "Vaswani", data: {} }, // weight 3 (highest)
    ],
    edges: [
      { src: 1, dst: 10, type: "about", weight: null },
      { src: 2, dst: 10, type: "mentions", weight: null },
      { src: 1, dst: 11, type: "mentions", weight: null },
      { src: 1, dst: 12, type: "mentions", weight: null },
      { src: 2, dst: 12, type: "mentions", weight: null },
      { src: 3, dst: 12, type: "mentions", weight: null },
      { src: 10, dst: 11, type: "similar-to", weight: 0.9 },
      { src: 10, dst: 12, type: "similar-to", weight: 0.9 },
    ],
  };

  it("names a galaxy after its most-revisited member, of any kind", () => {
    const g = buildGraph(naming);
    // the entity outranks every concept here — kind is no longer a tiebreaker
    expect(nameGalaxy(g, g.nodes())).toBe("Vaswani");
  });

  it("never names a galaxy after a source", () => {
    const g = buildGraph(naming);
    // sources (weight 0) are excluded even when they dominate the membership
    expect(nameGalaxy(g, ["1", "2", "3", "11"])).toBe("rnn");
  });
});
