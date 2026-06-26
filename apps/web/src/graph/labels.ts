import type { Settings } from "sigma/settings";
import type { NodeDisplayData, PartialButFor } from "sigma/types";

/* Custom hover label. Sigma's default draws a near-white box behind the label,
   which is unreadable against our near-white vellum text. Instead we draw an
   ink-on-parchment map tag with a brass hairline — readable and on-theme.
   It's canvas drawing, so it never touches React. */

const PARCHMENT = "#ece4d2"; // --vellum
const INK = "#0c1030"; // --void
const BRASS = "#cba34c"; // --brass

type HoverData = PartialButFor<NodeDisplayData, "x" | "y" | "size" | "label" | "color">;

export function drawHover(
  context: CanvasRenderingContext2D,
  data: HoverData,
  settings: Settings,
): void {
  const label = data.label;
  if (!label) return;

  const size = settings.labelSize;
  context.font = `${settings.labelWeight} ${size}px ${settings.labelFont}`;

  const padH = 9;
  const padV = 5;
  const textW = context.measureText(label).width;
  const boxW = textW + padH * 2;
  const boxH = size + padV * 2;
  const x = Math.round(data.x);
  const y = Math.round(data.y);
  const boxX = x + data.size + 5;
  const boxY = y - boxH / 2;

  // Parchment tag with a soft drop shadow.
  context.save();
  context.shadowBlur = 12;
  context.shadowColor = "rgba(0, 0, 0, 0.45)";
  context.shadowOffsetY = 2;
  context.beginPath();
  roundRect(context, boxX, boxY, boxW, boxH, 6);
  context.fillStyle = PARCHMENT;
  context.fill();
  context.restore();

  // Brass hairline border.
  context.beginPath();
  roundRect(context, boxX + 0.5, boxY + 0.5, boxW - 1, boxH - 1, 6);
  context.lineWidth = 1;
  context.strokeStyle = BRASS;
  context.stroke();

  // Ink text.
  context.fillStyle = INK;
  context.textAlign = "left";
  context.textBaseline = "middle";
  context.fillText(label, boxX + padH, y + 1);
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
): void {
  if (typeof ctx.roundRect === "function") {
    ctx.roundRect(x, y, w, h, r);
    return;
  }
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
