/**
 * A stylized wash-trading ring: five wallets trading in a closed loop,
 * one flagged, set against a few unconnected wallets for scale. Not a
 * literal data viz — it's the hero's one animated moment, standing in
 * for what graph-based ring detection actually looks for.
 */

const RING = [
  { x: 170, y: 60 },
  { x: 274.6, y: 136 },
  { x: 234.6, y: 259 },
  { x: 105.4, y: 259 },
  { x: 65.4, y: 136 },
];

const FLAGGED_INDEX = 1;

const NOISE = [
  { x: 36, y: 44, r: 3 },
  { x: 312, y: 90, r: 2.5 },
  { x: 300, y: 300, r: 3 },
  { x: 48, y: 296, r: 2.5 },
  { x: 20, y: 190, r: 2 },
];

export function RingGraphic() {
  const edges = RING.map((node, i) => {
    const next = RING[(i + 1) % RING.length];
    return { from: node, to: next, delay: i * 90 };
  });

  return (
    <svg
      viewBox="0 0 340 340"
      className="h-full w-full max-w-md"
      role="img"
      aria-label="Diagram of five wallets connected in a closed trading loop, with one wallet flagged as a detected wash-trading ring"
    >
      {NOISE.map((n, i) => (
        <circle
          key={`noise-${i}`}
          cx={n.x}
          cy={n.y}
          r={n.r}
          className="fill-border animate-rise"
          style={{ animationDelay: `${520 + i * 60}ms` }}
        />
      ))}

      {edges.map((edge, i) => (
        <line
          key={`edge-${i}`}
          x1={edge.from.x}
          y1={edge.from.y}
          x2={edge.to.x}
          y2={edge.to.y}
          className="stroke-border animate-draw"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeDasharray={150}
          style={{ animationDelay: `${180 + edge.delay}ms`, ["--draw-length" as string]: 150 }}
        />
      ))}

      {RING.map((node, i) => {
        const flagged = i === FLAGGED_INDEX;
        return (
          <g key={`node-${i}`}>
            {flagged && (
              <circle
                cx={node.x}
                cy={node.y}
                r={16}
                className="fill-none stroke-flag/40 animate-rise"
                strokeWidth={1}
                style={{ animationDelay: "760ms" }}
              />
            )}
            <circle
              cx={node.x}
              cy={node.y}
              r={flagged ? 8 : 5.5}
              className={
                flagged
                  ? "fill-flag animate-rise"
                  : "fill-surface stroke-muted animate-rise"
              }
              strokeWidth={flagged ? 0 : 1.25}
              style={{ animationDelay: `${420 + i * 60}ms` }}
            />
          </g>
        );
      })}
    </svg>
  );
}
