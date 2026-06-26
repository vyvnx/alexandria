/* The swap point. Today it always returns the Sigma engine. When the GPU core
   lands (frontend-architecture §19, Phase 1), feature-detect here and return a
   CosmosEngine — every caller depends on the GraphEngine interface, so nothing
   else changes. WebGPU (Phase 4) detects `navigator.gpu` the same way. */

import { SigmaEngine } from "./sigmaEngine";
import type { GraphEngine } from "./engine";

export function hasWebGL2(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!canvas.getContext("webgl2");
  } catch {
    return false;
  }
}

export function createEngine(): GraphEngine {
  // Phase 1: if (hasWebGPU()) return new CosmosEngine({ backend: "webgpu" })
  // Phase 1: if (graphLikelyLarge) return new CosmosEngine({ backend: "webgl2" })
  return new SigmaEngine();
}
