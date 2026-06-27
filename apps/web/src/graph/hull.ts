/* Pure geometry for galaxy boundaries. The engine computes a hull in *graph*
   space and caches it, recomputing only while the layout moves nodes (or on a
   membership/filter change); pan/zoom just re-project the cached ring, since a
   convex hull is affine-invariant. No dependency — Andrew's monotone chain,
   hand-rolled (plan §3). */

export interface Point {
  x: number;
  y: number;
}

const cross = (o: Point, a: Point, b: Point): number =>
  (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);

/** Convex hull (Andrew's monotone chain) as an ordered ring of vertices, or
    `null` when the points don't form a polygon (fewer than 3, or all collinear)
    — the caller draws a small circle instead. Interior and edge-collinear
    points are dropped. */
export function convexHull(points: Point[]): Point[] | null {
  if (points.length < 3) return null;

  const pts = points.slice().sort((a, b) => a.x - b.x || a.y - b.y);

  const lower: Point[] = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0)
      lower.pop();
    lower.push(p);
  }

  const upper: Point[] = [];
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0)
      upper.pop();
    upper.push(p);
  }

  // Drop each chain's last point (it's the first of the other chain).
  lower.pop();
  upper.pop();
  const hull = lower.concat(upper);

  // All points collinear ⇒ a degenerate line, not a polygon.
  return hull.length >= 3 ? hull : null;
}

/** Mean of a set of points (the hull's anchor for padding + label placement). */
export function centroid(points: Point[]): Point {
  let x = 0;
  let y = 0;
  for (const p of points) {
    x += p.x;
    y += p.y;
  }
  const n = points.length || 1;
  return { x: x / n, y: y / n };
}

/** Push each hull vertex `px` pixels outward from `center`, so the dashed
    boundary clears the stars it encloses rather than clipping through them. */
export function padHull(hull: Point[], center: Point, px: number): Point[] {
  return hull.map((p) => {
    const dx = p.x - center.x;
    const dy = p.y - center.y;
    const len = Math.hypot(dx, dy) || 1;
    return { x: p.x + (dx / len) * px, y: p.y + (dy / len) * px };
  });
}
