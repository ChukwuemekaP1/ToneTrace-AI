import React from "react";

export interface RadarDataPoint {
  label: string;
  value: number; // 0 to 100
}

export interface FacialRadarChartProps {
  data: RadarDataPoint[];
  size?: number;
  overallScore?: number;
  className?: string;
}

export const FacialRadarChart: React.FC<FacialRadarChartProps> = ({
  data,
  size = 280,
  overallScore,
  className = "",
}) => {
  if (!data || data.length < 3) return null;

  const center = size / 2;
  const radius = (size / 2) - 42; // Leave margin for labels
  const angleStep = (Math.PI * 2) / data.length;

  // Concentric polygon background levels (25%, 50%, 75%, 100%)
  const levels = [0.25, 0.5, 0.75, 1.0];

  const getCoordinates = (index: number, level: number): { x: number; y: number } => {
    // Start at top (-PI/2)
    const angle = index * angleStep - Math.PI / 2;
    return {
      x: center + radius * level * Math.cos(angle),
      y: center + radius * level * Math.sin(angle),
    };
  };

  // Generate path string for a polygon level
  const generateLevelPolygon = (level: number): string => {
    return data
      .map((_, i) => {
        const { x, y } = getCoordinates(i, level);
        return `${i === 0 ? "M" : "L"} ${x} ${y}`;
      })
      .concat("Z")
      .join(" ");
  };

  // Generate data polygon path
  const dataPolygonPath = data
    .map((point, i) => {
      const normalizedVal = Math.max(0.1, Math.min(1.0, point.value / 100));
      const { x, y } = getCoordinates(i, normalizedVal);
      return `${i === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .concat("Z")
    .join(" ");

  return (
    <div className={`flex flex-col items-center justify-center p-3 rounded-2xl bg-white border border-slate-200/90 shadow-soft ${className}`}>
      <div className="w-full flex items-center justify-between pb-2 border-b border-slate-100">
        <div>
          <span className="text-xxs font-bold uppercase tracking-wider text-slate-500 block">
            Facial Optimization Profile
          </span>
          {overallScore !== undefined && (
            <span className="text-xs font-semibold text-slate-800">
              Composite Score: <span className="font-mono text-brand font-bold">{overallScore}%</span>
            </span>
          )}
        </div>
        <span className="text-xxs text-slate-400 font-mono">Harmonic 5-Axis</span>
      </div>

      <svg width={size} height={size} className="overflow-visible my-1 select-none">
        {/* Background Grid Polygons */}
        {levels.map((lvl) => (
          <path
            key={lvl}
            d={generateLevelPolygon(lvl)}
            fill="none"
            stroke="#E2E8F0"
            strokeWidth="1"
            strokeDasharray={lvl === 1 ? "none" : "3 3"}
          />
        ))}

        {/* Axis Spokes from center to vertices */}
        {data.map((_, i) => {
          const { x, y } = getCoordinates(i, 1.0);
          return (
            <line
              key={i}
              x1={center}
              y1={center}
              x2={x}
              y2={y}
              stroke="#E2E8F0"
              strokeWidth="1"
            />
          );
        })}

        {/* Data Radar Polygon */}
        <path
          d={dataPolygonPath}
          fill="rgba(61, 107, 88, 0.18)"
          stroke="#3D6B58"
          strokeWidth="2.5"
          className="transition-all duration-300"
        />

        {/* Data Points / Nodes */}
        {data.map((point, i) => {
          const normalizedVal = Math.max(0.1, Math.min(1.0, point.value / 100));
          const { x, y } = getCoordinates(i, normalizedVal);
          return (
            <circle
              key={i}
              cx={x}
              cy={y}
              r="4"
              fill="#FFFFFF"
              stroke="#3D6B58"
              strokeWidth="2"
              className="drop-shadow-sm"
            />
          );
        })}

        {/* Labels at outer perimeter */}
        {data.map((point, i) => {
          const { x, y } = getCoordinates(i, 1.2);
          const isTop = y < center - 20;
          const isBottom = y > center + 20;
          const isRight = x > center + 20;
          const textAnchor = isRight ? "start" : x < center - 20 ? "end" : "middle";

          return (
            <g key={i}>
              <text
                x={x}
                y={y + (isTop ? -4 : isBottom ? 8 : 0)}
                textAnchor={textAnchor}
                className="text-[10px] font-medium fill-slate-700"
              >
                {point.label}
              </text>
              <text
                x={x}
                y={y + (isTop ? 8 : isBottom ? 20 : 12)}
                textAnchor={textAnchor}
                className="text-[10px] font-bold font-mono fill-brand"
              >
                {Math.round(point.value)}%
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
};
