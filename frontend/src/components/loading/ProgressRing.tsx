import { useEffect, useRef, useState, useMemo } from "react";
import { Check, Loader2 } from "lucide-react";

export interface ProgressStage {
  id: string;
  label: string;
  description?: string;
  icon?: React.ReactNode;
  duration?: number; // ms, opcional para auto-avance
}

export interface ProgressRingProps {
  /** Etapas del proceso (se distribuyen uniformemente en el anillo) */
  stages: ProgressStage[];
  /** Etapa actual (0-index) */
  currentStage: number;
  /** Progreso dentro de la etapa actual (0-1) */
  stageProgress: number;
  /** Progreso global (0-1) - si no se da, se calcula de stages */
  globalProgress?: number;
  /** Tamaño del anillo en px */
  size?: number;
  /** Grosor del trazo */
  strokeWidth?: number;
  /** Colores personalizados */
  colors?: {
    track?: string;           // fondo del anillo
    progress?: string;        // progreso completado
    current?: string;         // etapa actual
    upcoming?: string;        // etapas pendientes
    text?: string;            // texto principal
    textMuted?: string;       // texto secundario
    glow?: string;            // color del glow
  };
  /** Mostrar etiquetas de etapas alrededor del anillo */
  showStageLabels?: boolean;
  /** Mostrar progreso numérico en el centro */
  showPercent?: boolean;
  /** Texto personalizado en el centro */
  centerText?: string;
  /** Subtexto en el centro */
  centerSubtext?: string;
  /** Animar cambios de etapa */
  animate?: boolean;
  /** Velocidad de animación (1 = normal) */
  animationSpeed?: number;
  /** Reducir movimiento (accesibilidad) */
  reducedMotion?: boolean;
  /** Callback al completar todas las etapas */
  onComplete?: () => void;
  /** Callback al cambiar etapa */
  onStageChange?: (stage: number) => void;
  /** Clase CSS adicional */
  className?: string;
  /** Estilo inline adicional */
  style?: React.CSSProperties;
}

const DEFAULT_COLORS = {
  track: "var(--ring-track, #e5e7eb)",
  progress: "var(--ring-progress, #3b82f6)",
  current: "var(--ring-current, #60a5fa)",
  upcoming: "var(--ring-upcoming, #9ca3af)",
  text: "var(--ring-text, #111827)",
  textMuted: "var(--ring-text-muted, #6b7280)",
  glow: "var(--ring-glow, rgba(59, 130, 246, 0.4))",
};

const DEFAULT_STAGES: ProgressStage[] = [
  { id: "search", label: "Buscando", description: "Escaneando fuentes", icon: <Loader2 size={14} /> },
  { id: "filter", label: "Filtrando", description: "Aplicando criterios", icon: <Loader2 size={14} /> },
  { id: "analyze", label: "Analizando", description: "IA evaluando match", icon: <Loader2 size={14} /> },
  { id: "complete", label: "Listo", description: "Resultados disponibles", icon: <Check size={14} /> },
];

function polarToCartesian(cx: number, cy: number, radius: number, angleDeg: number) {
  const angleRad = (angleDeg - 90) * (Math.PI / 180);
  return {
    x: cx + radius * Math.cos(angleRad),
    y: cy + radius * Math.sin(angleRad),
  };
}

function describeArc(
  cx: number,
  cy: number,
  radius: number,
  startAngle: number,
  endAngle: number
) {
  const start = polarToCartesian(cx, cy, radius, endAngle);
  const end = polarToCartesian(cx, cy, radius, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";
  return [
    "M", start.x, start.y,
    "A", radius, radius, 0, largeArcFlag, 0, end.x, end.y,
  ].join(" ");
}

function easeOutCubic(t: number) {
  return 1 - Math.pow(1 - t, 3);
}

export function ProgressRing({
  stages = DEFAULT_STAGES,
  currentStage = 0,
  stageProgress = 0,
  globalProgress,
  size = 200,
  strokeWidth = 8,
  colors,
  showStageLabels = true,
  showPercent = true,
  centerText,
  centerSubtext,
  animate = true,
  animationSpeed = 1,
  reducedMotion = false,
  onComplete,
  onStageChange,
  className = "",
  style,
}: ProgressRingProps) {
  const c = useMemo(() => ({ ...DEFAULT_COLORS, ...colors }), [colors]);
  const radius = (size - strokeWidth) / 2;
  const center = size / 2;
  const circumference = 2 * Math.PI * radius;

  const [displayProgress, setDisplayProgress] = useState(globalProgress ?? 0);
  const [displayStage, setDisplayStage] = useState(currentStage);
  const [displayStageProgress, setDisplayStageProgress] = useState(stageProgress);
  const [, setIsAnimating] = useState(false);
  const animationRef = useRef<number>(0);
  const startTimeRef = useRef<number>(0);
  const prevStageRef = useRef(currentStage);

  // Calcular progreso global si no se proporciona
  const computedGlobalProgress = useMemo(() => {
    if (globalProgress !== undefined) return globalProgress;
    const completedStages = Math.max(0, currentStage);
    return Math.min(1, (completedStages + stageProgress) / stages.length);
  }, [globalProgress, currentStage, stageProgress, stages.length]);

  // Animación suave de progreso
  useEffect(() => {
    if (!animate || reducedMotion) {
      setDisplayProgress(computedGlobalProgress);
      setDisplayStage(currentStage);
      setDisplayStageProgress(stageProgress);
      return;
    }

    const targetProgress = computedGlobalProgress;
    const targetStage = currentStage;
    const targetStageProgress = stageProgress;

    // Detectar cambio de etapa
    if (targetStage !== prevStageRef.current) {
      onStageChange?.(targetStage);
      prevStageRef.current = targetStage;
    }

    setIsAnimating(true);
    startTimeRef.current = performance.now();
    const duration = 600 / animationSpeed;

    const animateProgress = (now: number) => {
      const elapsed = now - (startTimeRef.current || now);
      const progress = Math.min(1, elapsed / duration);
      const eased = easeOutCubic(progress);

      setDisplayProgress((prev) => prev + (targetProgress - prev) * eased);
      setDisplayStageProgress((prev) => prev + (targetStageProgress - prev) * eased);

      if (targetStage !== displayStage) {
        setDisplayStage(targetStage);
      }

      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animateProgress);
      } else {
        setIsAnimating(false);
        if (targetProgress >= 1 && targetStage === stages.length - 1) {
          onComplete?.();
        }
      }
    };

    animationRef.current = requestAnimationFrame(animateProgress);
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [computedGlobalProgress, currentStage, stageProgress, animate, reducedMotion, animationSpeed, stages.length, onComplete, onStageChange, displayStage]);

  // Etapa actual
  const currentStageData = stages[Math.min(displayStage, stages.length - 1)];
  const isComplete = displayProgress >= 1 && displayStage >= stages.length - 1;

  // Generar paths para cada segmento de etapa
  const stageSegments = useMemo(() => {
    const segments: Array<{
      path: string;
      color: string;
      opacity: number;
      dashOffset: number;
      isCurrent: boolean;
      isComplete: boolean;
    }> = [];

    const stageAngle = 360 / stages.length;

    stages.forEach((_, index) => {
      const startAngle = index * stageAngle;
      const isStageComplete = index < displayStage;
      const isCurrentStage = index === Math.floor(displayStage);

      let segmentProgress = 0;
      if (isStageComplete) {
        segmentProgress = 1;
      } else if (isCurrentStage) {
        segmentProgress = displayStageProgress;
      }

      const sweepAngle = stageAngle * segmentProgress;
      const path = describeArc(center, center, radius, startAngle, startAngle + sweepAngle);

      let color: string;
      let opacity = 1;
      if (isStageComplete) {
        color = c.progress;
      } else if (isCurrentStage) {
        color = c.current;
      } else {
        color = c.upcoming;
        opacity = 0.4;
      }

      segments.push({
        path,
        color,
        opacity,
        dashOffset: 0,
        isCurrent: isCurrentStage,
        isComplete: isStageComplete,
      });
    });

    return segments;
  }, [stages.length, displayStage, displayStageProgress, displayProgress, center, radius, c]);

  // Puntos de las etapas para labels
  const stagePoints = useMemo(() => {
    const points: Array<{ x: number; y: number; angle: number; label: string; isActive: boolean; isComplete: boolean }> = [];
    const labelRadius = radius + strokeWidth + 18;
    stages.forEach((stage, index) => {
      const angle = (index * 360 / stages.length) - 90;
      const rad = angle * (Math.PI / 180);
      points.push({
        x: center + labelRadius * Math.cos(rad),
        y: center + labelRadius * Math.sin(rad),
        angle,
        label: stage.label,
        isActive: index === displayStage,
        isComplete: index < displayStage,
      });
    });
    return points;
  }, [stages, displayStage, center, radius, strokeWidth]);

  return (
    <div
      className={`progress-ring-container ${className}`}
      style={{
        width: size,
        height: size,
        position: "relative",
        ...style,
      }}
      role="progressbar"
      aria-valuenow={Math.round(displayProgress * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={centerSubtext || `${currentStageData?.label} - ${Math.round(displayProgress * 100)}%`}
    >
      {/* Glow background */}
      {animate && !reducedMotion && displayProgress > 0 && (
        <svg width={size} height={size} style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none", filter: "blur(12px)" }}>
          <circle
            cx={center}
            cy={center}
            r={radius}
            stroke={c.glow}
            strokeWidth={strokeWidth * 1.5}
            fill="none"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - displayProgress)}
            strokeLinecap="round"
            opacity={0.3}
            style={{
              transform: "rotate(-90deg)",
              transformOrigin: `${center}px ${center}px`,
              transition: "stroke-dashoffset 0.3s ease-out",
            }}
          />
        </svg>
      )}

      {/* Track base */}
      <svg width={size} height={size} style={{ position: "absolute", top: 0, left: 0 }}>
        <circle
          cx={center}
          cy={center}
          r={radius}
          stroke={c.track}
          strokeWidth={strokeWidth}
          fill="none"
          style={{ opacity: 0.2 }}
        />
      </svg>

      {/* Stage segments */}
      <svg width={size} height={size} style={{ position: "absolute", top: 0, left: 0 }}>
        {stageSegments.map((seg, i) => (
          <path
            key={i}
            d={seg.path}
            stroke={seg.color}
            strokeWidth={strokeWidth}
            fill="none"
            strokeLinecap="round"
            opacity={seg.opacity}
            style={{
              transform: "rotate(-90deg)",
              transformOrigin: `${center}px ${center}px`,
              transition: animate && !reducedMotion
                ? `stroke-dashoffset 0.3s ease-out, opacity 0.3s ease-out, stroke 0.3s ease-out`
                : "none",
              filter: seg.isCurrent && !isComplete ? `drop-shadow(0 0 6px ${c.glow})` : "none",
            }}
          />
        ))}
      </svg>

      {/* Stage markers on ring */}
      {showStageLabels && (
        <svg width={size} height={size} style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}>
          {stagePoints.map((point, i) => (
            <g key={i} style={{ transform: `rotate(${point.angle}deg) translate(0, -${radius + strokeWidth + 8}px) rotate(${-point.angle}deg)`, transformOrigin: `${center}px ${center}px` }}>
              {/* Dot on ring */}
              <circle
                cx={center}
                cy={center - radius - strokeWidth / 2}
                r={point.isActive ? 5 : point.isComplete ? 4 : 3}
                fill={point.isComplete ? c.progress : point.isActive ? c.current : c.upcoming}
                style={{
                  transition: "r 0.2s ease-out, fill 0.2s ease-out",
                  filter: point.isActive && animate && !reducedMotion ? `drop-shadow(0 0 4px ${c.glow})` : "none",
                }}
              />
              {/* Label */}
              <text
                x={point.x}
                y={point.y + 4}
                textAnchor="middle"
                dominantBaseline="hanging"
                fontSize="11"
                fontWeight={point.isActive ? 600 : 400}
                fill={point.isActive ? c.text : c.textMuted}
                style={{
                  transition: "fill 0.2s ease-out, font-weight 0.2s ease-out",
                  userSelect: "none",
                  pointerEvents: "none",
                }}
              >
                {point.label}
              </text>
            </g>
          ))}
        </svg>
      )}

      {/* Center content */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: size,
          height: size,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          pointerEvents: "none",
          zIndex: 10,
        }}
      >
        {centerText ? (
          <span style={{ fontSize: size * 0.14, fontWeight: 700, color: c.text, lineHeight: 1 }}>
            {centerText}
          </span>
        ) : showPercent ? (
          <span style={{ fontSize: size * 0.18, fontWeight: 700, color: c.text, lineHeight: 1 }}>
            {Math.round(displayProgress * 100)}%
          </span>
        ) : (
          currentStageData?.icon
        )}

        {(centerSubtext || currentStageData?.description) && (
          <span
            style={{
              fontSize: size * 0.065,
              color: c.textMuted,
              marginTop: 4,
              textAlign: "center",
              maxWidth: size * 0.7,
              fontWeight: 500,
            }}
          >
            {centerSubtext || currentStageData?.description}
          </span>
        )}

        {isComplete && !centerText && !showPercent && (
          <span style={{ fontSize: size * 0.18, fontWeight: 700, color: c.progress, lineHeight: 1 }}>
            <Check size={size * 0.18} />
          </span>
        )}
      </div>

      {/* Pulse ring for current stage */}
      {animate && !reducedMotion && !isComplete && displayStage < stages.length - 1 && (
        <svg width={size} height={size} style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}>
          <circle
            cx={center}
            cy={center}
            r={radius + strokeWidth / 2}
            stroke={c.current}
            strokeWidth={2}
            fill="none"
            strokeDasharray={`${circumference * 0.15} ${circumference * 0.85}`}
            strokeDashoffset={0}
            opacity={0.6}
            style={{
              transform: "rotate(-90deg)",
              transformOrigin: `${center}px ${center}px`,
              animation: `progressRingSpin ${2 / animationSpeed}s linear infinite`,
            }}
          />
          <style>{`
            @keyframes progressRingSpin {
              from { transform: rotate(-90deg); }
              to { transform: rotate(270deg); }
            }
          `}</style>
        </svg>
      )}
    </div>
  );
}

/** Variante compacta para espacios reducidos */
export function ProgressRingCompact({
  stages = DEFAULT_STAGES,
  currentStage = 0,
  stageProgress = 0,
  size = 60,
  strokeWidth = 4,
  showPercent = true,
  ...props
}: Omit<ProgressRingProps, "showStageLabels" | "centerText" | "centerSubtext">) {
  return (
    <ProgressRing
      stages={stages}
      currentStage={currentStage}
      stageProgress={stageProgress}
      size={size}
      strokeWidth={strokeWidth}
      showStageLabels={false}
      showPercent={showPercent}
      centerText={undefined}
      centerSubtext={undefined}
      {...props}
    />
  );
}

/** Variante lineal para barras de progreso con etapas */
export function ProgressRingLinear({
  stages = DEFAULT_STAGES,
  currentStage = 0,
  stageProgress = 0,
  height = 6,
  showLabels = true,
  showPercent = true,
  colors,
  ...props
}: Omit<ProgressRingProps, "size" | "strokeWidth" | "showStageLabels" | "centerText" | "centerSubtext"> & {
  height?: number;
  showLabels?: boolean;
}) {
  const c = useMemo(() => ({ ...DEFAULT_COLORS, ...colors }), [colors]);
  const totalStages = stages.length;

  return (
    <div style={{ width: "100%", ...props.style }} className={props.className}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ flex: 1, position: "relative", height }}>
          {/* Track */}
          <div
            style={{
              width: "100%",
              height,
              background: c.track,
              borderRadius: height / 2,
              overflow: "hidden",
              position: "relative",
            }}
          >
            {/* Completed stages */}
            {stages.map((_, i) => {
              const stageWidth = 100 / totalStages;
              const isComplete = i < currentStage;
              const isCurrent = i === currentStage;
              let width = 0;
              if (isComplete) width = stageWidth;
              else if (isCurrent) width = stageWidth * stageProgress;

              return (
                <div
                  key={i}
                  style={{
                    position: "absolute",
                    left: `${i * stageWidth}%`,
                    top: 0,
                    height: "100%",
                    width: `${width}%`,
                    background: isComplete ? c.progress : isCurrent ? c.current : "transparent",
                    borderRadius: height / 2,
                    transition: "width 0.4s ease-out, background 0.3s ease-out",
                    transformOrigin: "left center",
                  }}
                />
              );
            })}
            {/* Stage dividers */}
            {stages.slice(0, -1).map((_, i) => (
              <div
                key={`div-${i}`}
                style={{
                  position: "absolute",
                  left: `${(i + 1) * (100 / totalStages)}%`,
                  top: "50%",
                  transform: "translate(-50%, -50%)",
                  width: 2,
                  height: height * 2,
                  background: c.track,
                  borderRadius: 1,
                }}
              />
            ))}
          </div>
        </div>
        {showPercent && (
          <span style={{ fontSize: 12, fontWeight: 600, color: c.text, minWidth: 40, textAlign: "right" }}>
            {Math.round(((currentStage + stageProgress) / totalStages) * 100)}%
          </span>
        )}
      </div>
      {showLabels && (
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 11, color: c.textMuted }}>
          {stages.map((stage, i) => (
            <span
              key={stage.id}
              style={{
                textAlign: "center",
                flex: 1,
                color: i < currentStage ? c.progress : i === currentStage ? c.current : c.textMuted,
                fontWeight: i === currentStage ? 600 : 400,
                transition: "color 0.2s ease-out",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {stage.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}