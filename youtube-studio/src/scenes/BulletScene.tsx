import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import type { BulletScene as BulletSceneType } from "../types";
import { BackgroundRenderer } from "./Background";
import { GlowCircle, DrawLine, GridOverlay, Vignette } from "./Decorations";

const staggerDelay = 18;
const bulletAnim = 14;

const bulletSymbols = ["◆", "■", "●", "▲", "★"];

export const BulletScene: React.FC<{ scene: BulletSceneType }> = ({
  scene,
}) => {
  const frame = useCurrentFrame();

  const titleOpacity = interpolate(frame, [0, 18], [0, 1], {
    extrapolateRight: "clamp",
  });
  const titleY = interpolate(frame, [0, 18], [30, 0], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill>
      <BackgroundRenderer background={scene.background} />
      <GlowCircle size={500} x={75} y={15} color="#4fc3f7" speed={0.3} opacity={0.05} />
      <GlowCircle size={400} x={25} y={85} color="#fff" opacity={0.03} blur={70} speed={0.2} />
      <GridOverlay opacity={0.02} />
      <Vignette />

      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          width: "78%",
          zIndex: 2,
        }}
      >
        {scene.title && (
          <>
            <h2
              style={{
                opacity: titleOpacity,
                transform: `translateY(${titleY}px)`,
                fontSize: 44,
                fontWeight: 700,
                margin: 0,
                marginBottom: 20,
                color: "#fff",
                letterSpacing: "2px",
                textShadow: "0 2px 16px rgba(0,0,0,0.4)",
              }}
            >
              {scene.title}
            </h2>
            <DrawLine
              width={60}
              delay={10}
              duration={14}
              style={{ marginBottom: 36 }}
            />
          </>
        )}

        {scene.bullets.map((bullet, i) => {
          const start = Math.floor(i * staggerDelay) + (scene.title ? 20 : 0);
          const op = interpolate(frame, [start, start + bulletAnim], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          const x = interpolate(frame, [start, start + bulletAnim], [40, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });

          return (
            <div
              key={i}
              style={{
                opacity: op,
                transform: `translateX(${x}px)`,
                display: "flex",
                alignItems: "center",
                marginBottom: 22,
                padding: "14px 24px",
                borderRadius: 8,
                background:
                  op > 0.8
                    ? "rgba(255,255,255,0.04)"
                    : "transparent",
                transition: "background 0.3s",
              }}
            >
              <span
                style={{
                  color: "#4fc3f7",
                  fontSize: 22,
                  marginRight: 20,
                  flexShrink: 0,
                  opacity: op,
                }}
              >
                {bulletSymbols[i % bulletSymbols.length]}
              </span>
              <span
                style={{
                  fontSize: 30,
                  color: "#e8edf2",
                  lineHeight: 1.5,
                  letterSpacing: "0.5px",
                  textShadow: "0 1px 6px rgba(0,0,0,0.2)",
                }}
              >
                {bullet}
              </span>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
