import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import type { OutroScene as OutroSceneType } from "../types";
import { BackgroundRenderer } from "./Background";
import { GlowCircle, DrawLine, GridOverlay, Vignette } from "./Decorations";

export const OutroScene: React.FC<{ scene: OutroSceneType }> = ({
  scene,
}) => {
  const frame = useCurrentFrame();
  const dur = scene.animation?.duration ?? 30;

  const opacity = interpolate(frame, [0, dur], [0, 1], {
    extrapolateRight: "clamp",
  });
  const scale = interpolate(frame, [0, dur], [0.7, 1], {
    extrapolateRight: "clamp",
  });

  const subOpacity = interpolate(frame, [Math.floor(dur * 0.6), dur], [0, 1], {
    extrapolateRight: "clamp",
  });

  const brandOpacity = interpolate(
    frame,
    [Math.floor(dur * 0.8), dur + 10],
    [0, 1],
    { extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill>
      <BackgroundRenderer background={scene.background} />
      <GlowCircle size={600} x={50} y={50} color="#4fc3f7" speed={0.3} opacity={0.06} />
      <GlowCircle size={400} x={20} y={80} color="#fff" opacity={0.03} blur={70} speed={0.2} />
      <GridOverlay />
      <Vignette />

      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          textAlign: "center",
          width: "80%",
          zIndex: 2,
        }}
      >
        <h1
          style={{
            opacity,
            transform: `scale(${scale})`,
            fontSize: 72,
            fontWeight: 800,
            margin: 0,
            color: "#fff",
            letterSpacing: "3px",
            textShadow: "0 4px 30px rgba(0,0,0,0.5)",
          }}
        >
          {scene.title}
        </h1>

        <DrawLine
          width={80}
          color="#4fc3f7"
          delay={Math.floor(dur * 0.4)}
          duration={16}
          align="center"
          style={{ marginTop: 24, marginBottom: 20 }}
        />

        {scene.subtitle && (
          <p
            style={{
              opacity: subOpacity,
              fontSize: 28,
              color: "#8ab4d6",
              margin: 0,
              letterSpacing: "1px",
            }}
          >
            {scene.subtitle}
          </p>
        )}

        {scene.brandText && (
          <p
            style={{
              opacity: brandOpacity,
              fontSize: 20,
              color: "#5a7a94",
              marginTop: 60,
              letterSpacing: "3px",
              textTransform: "uppercase",
            }}
          >
            {scene.brandText}
          </p>
        )}
      </div>
    </AbsoluteFill>
  );
};
