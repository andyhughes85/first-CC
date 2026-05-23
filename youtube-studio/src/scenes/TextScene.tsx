import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import type { TextScene as TextSceneType } from "../types";
import { BackgroundRenderer } from "./Background";
import { GlowCircle, DrawLine, GridOverlay, Vignette } from "./Decorations";

export const TextScene: React.FC<{ scene: TextSceneType }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const totalDuration = scene.durationInFrames;

  const titleOpacity = interpolate(frame, [0, 18], [0, 1], {
    extrapolateRight: "clamp",
  });
  const titleY = interpolate(frame, [0, 18], [20, 0], {
    extrapolateRight: "clamp",
  });

  const bodyOpacity = interpolate(frame, [25, 50], [0, 1], {
    extrapolateRight: "clamp",
  });

  // 长文本自动上滚
  const isLong = scene.bodyText.length > 120;
  let scrollY = 0;
  if (isLong) {
    scrollY = interpolate(frame, [60, totalDuration - 15], [0, -200], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  }

  const lines = scene.bodyText.split("\n");

  return (
    <AbsoluteFill>
      <BackgroundRenderer background={scene.background} />
      <GlowCircle size={450} x={75} y={30} color="#4fc3f7" speed={0.35} opacity={0.04} />
      <GlowCircle size={350} x={25} y={70} color="#fff" opacity={0.02} blur={80} speed={0.25} />
      <GridOverlay opacity={0.015} />
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
                fontSize: 42,
                fontWeight: 700,
                margin: 0,
                marginBottom: 12,
                color: "#fff",
                letterSpacing: "2px",
                textShadow: "0 2px 16px rgba(0,0,0,0.4)",
              }}
            >
              {scene.title}
            </h2>
            <DrawLine
              width={50}
              delay={8}
              duration={12}
              style={{ marginBottom: scene.title ? 32 : 0 }}
            />
          </>
        )}

        <div
          style={{
            opacity: bodyOpacity,
            transform: `translateY(${scrollY}px)`,
          }}
        >
          {lines.map((line, i) => {
            // 空行 = 段落间距
            if (line.trim() === "")
              return <div key={i} style={{ height: 28 }} />;

            return (
              <p
                key={i}
                style={{
                  fontSize: 32,
                  lineHeight: 1.7,
                  color: "#e0e6ec",
                  margin: 0,
                  textAlign: "center",
                  fontWeight: i === 0 ? 600 : 400,
                  textShadow: "0 1px 8px rgba(0,0,0,0.2)",
                }}
              >
                {line}
              </p>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
