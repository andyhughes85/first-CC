import React from "react";
import { useCurrentFrame, interpolate } from "remotion";

/** 缓慢漂移的发光圆（背景装饰） */
export const GlowCircle: React.FC<{
  size: number;
  x: number;
  y: number;
  color: string;
  opacity?: number;
  speed?: number;
  blur?: number;
}> = ({ size, x, y, color, opacity = 0.06, speed = 1, blur = 60 }) => {
  const frame = useCurrentFrame();

  const dx = interpolate(
    Math.sin(frame * 0.008 * speed),
    [-1, 1],
    [-30, 30],
  );
  const dy = interpolate(
    Math.cos(frame * 0.006 * speed),
    [-1, 1],
    [-20, 20],
  );
  const s = interpolate(
    Math.sin(frame * 0.01 * speed),
    [-1, 1],
    [0.85, 1.15],
  );

  return (
    <div
      style={{
        position: "absolute",
        width: size,
        height: size,
        borderRadius: "50%",
        background: `radial-gradient(circle, ${color}, transparent)`,
        opacity,
        left: `calc(${x}% + ${dx}px)`,
        top: `calc(${y}% + ${dy}px)`,
        transform: `translate(-50%, -50%) scale(${s})`,
        filter: `blur(${blur}px)`,
        pointerEvents: "none",
      }}
    />
  );
};

/** 绘制动画横线（装饰分隔线） */
export const DrawLine: React.FC<{
  width: number;
  color?: string;
  delay?: number;
  duration?: number;
  align?: "left" | "center";
  style?: React.CSSProperties;
}> = ({ width, color = "#4fc3f7", delay = 0, duration = 20, align = "left", style: extraStyle }) => {
  const frame = useCurrentFrame();

  const progress = interpolate(frame, [delay, delay + duration], [0, width], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = interpolate(frame, [delay, delay + 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        width: progress,
        height: 3,
        background: `linear-gradient(90deg, ${color}, transparent)`,
        opacity,
        borderRadius: 2,
        marginLeft: align === "center" ? "auto" : 0,
        marginRight: align === "center" ? "auto" : 0,
        ...extraStyle,
      }}
    />
  );
};

/** 微光扫描线（从上到下） */
export const Scanline: React.FC<{
  delay?: number;
  duration?: number;
  color?: string;
}> = ({ delay = 0, duration = 60, color = "rgba(79, 195, 247, 0.04)" }) => {
  const frame = useCurrentFrame();
  const progress = interpolate(
    ((frame - delay) % (duration + 30)) / (duration + 30),
    [0, 1],
    [0, 100],
  );

  if (frame < delay) return null;

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        height: "40%",
        top: `${progress - 20}%`,
        background: `linear-gradient(180deg, transparent, ${color}, transparent)`,
        pointerEvents: "none",
      }}
    />
  );
};

/** 网格纹理叠加 */
export const GridOverlay: React.FC<{
  opacity?: number;
  size?: number;
}> = ({ opacity = 0.03, size = 60 }) => {
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        backgroundImage: `
          linear-gradient(rgba(255,255,255,${opacity}) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255,255,255,${opacity}) 1px, transparent 1px)
        `,
        backgroundSize: `${size}px ${size}px`,
        pointerEvents: "none",
      }}
    />
  );
};

/** 渐暗遮罩（边缘柔化） */
export const Vignette: React.FC = () => (
  <div
    style={{
      position: "absolute",
      inset: 0,
      background:
        "radial-gradient(ellipse at center, transparent 60%, rgba(0,0,0,0.5) 100%)",
      pointerEvents: "none",
    }}
  />
);
