/** A schematic of direction only: the start triangle at the centre, the lot at its bearing. */
export function CourseDiagram({ bearing }: { bearing: number }) {
  const radius = 44;
  const angle = (bearing * Math.PI) / 180;
  const cx = 60;
  const cy = 60;
  const x = cx + Math.sin(angle) * radius;
  const y = cy - Math.cos(angle) * radius;
  return (
    <svg className="course__svg" viewBox="0 0 120 120" role="img" aria-label={`${Math.round(bearing)}°`}>
      <circle cx={cx} cy={cy} r={radius} className="course__ring" />
      <circle cx={cx} cy={cy} r={radius / 2} className="course__ring course__ring--inner" />
      <path d="M60 6v10M60 6l-4 6M60 6l4 6" className="course__north" />
      <text x="60" y="20" className="course__n" textAnchor="middle">
        N
      </text>
      <line x1={cx} y1={cy} x2={x} y2={y} className="course__line" />
      <path d="M60 52 67 66H53z" className="course__start" />
      <circle cx={x} cy={y} r="9" className="course__ctl" />
      <circle cx={x} cy={y} r="4.6" className="course__ctl" />
    </svg>
  );
}
