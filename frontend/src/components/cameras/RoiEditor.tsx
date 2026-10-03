import { Eraser, Undo2 } from "lucide-react";
import { useRef, useState, type PointerEvent } from "react";

import { Button } from "@/components/ui/button";

export type Point = [number, number];

/**
 * FR-5: draw the region of interest on the camera snapshot. Click to add a corner, drag a corner to
 * move it. Coordinates are normalised to 0..1 so they do not depend on the stream resolution.
 */
export function RoiEditor({
  snapshot,
  value,
  onChange,
}: {
  snapshot: string | null;
  value: Point[];
  onChange: (points: Point[]) => void;
}) {
  const surface = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<number | null>(null);

  const toPoint = (event: PointerEvent): Point | null => {
    const rect = surface.current?.getBoundingClientRect();
    if (!rect) return null;
    const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
    return [Number(x.toFixed(4)), Number(y.toFixed(4))];
  };

  const onPointerDown = (event: PointerEvent) => {
    if (dragging !== null) return;
    const point = toPoint(event);
    if (point) onChange([...value, point]);
  };

  const onPointerMove = (event: PointerEvent) => {
    if (dragging === null) return;
    const point = toPoint(event);
    if (point) onChange(value.map((p, i) => (i === dragging ? point : p)));
  };

  if (!snapshot) {
    return (
      <p className="text-muted-foreground rounded-md border border-dashed p-4 text-sm">
        Test the connection first; the ROI is drawn on the camera snapshot. Without an ROI the whole frame is used.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <div
        ref={surface}
        className="relative w-full cursor-crosshair touch-none overflow-hidden rounded-md border select-none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => setDragging(null)}
        onPointerLeave={() => setDragging(null)}
        role="application"
        aria-label="Region of interest editor. Click to add corners."
      >
        <img src={snapshot} alt="Camera snapshot" className="block w-full" draggable={false} />
        <svg viewBox="0 0 1 1" preserveAspectRatio="none" className="absolute inset-0 size-full">
          {value.length >= 3 && (
            <polygon
              points={value.map(([x, y]) => `${x},${y}`).join(" ")}
              className="fill-primary/20 stroke-primary"
              strokeWidth={0.004}
            />
          )}
          {value.length === 2 && (
            <line x1={value[0][0]} y1={value[0][1]} x2={value[1][0]} y2={value[1][1]} className="stroke-primary" strokeWidth={0.004} />
          )}
        </svg>
        {value.map(([x, y], index) => (
          <button
            key={index}
            type="button"
            aria-label={`Corner ${index + 1}`}
            className="bg-primary border-background absolute size-3.5 -translate-x-1/2 -translate-y-1/2 cursor-move rounded-full border-2"
            style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
            onPointerDown={(event) => {
              event.stopPropagation();
              (event.target as HTMLElement).setPointerCapture?.(event.pointerId);
              setDragging(index);
            }}
          />
        ))}
      </div>
      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" disabled={value.length === 0} onClick={() => onChange(value.slice(0, -1))}>
          <Undo2 aria-hidden /> Undo corner
        </Button>
        <Button type="button" variant="outline" size="sm" disabled={value.length === 0} onClick={() => onChange([])}>
          <Eraser aria-hidden /> Clear (use whole frame)
        </Button>
        <span className="text-muted-foreground text-xs">
          {value.length === 0 ? "Whole frame" : value.length < 3 ? "Add at least 3 corners" : `${value.length} corners`}
        </span>
      </div>
    </div>
  );
}
