import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import type { TitleScene as TitleSceneType } from "../types";
import { BackgroundRenderer } from "./Background";
import { GlowCircle, DrawLine, GridOverlay, Vignette } from "./Decorations";

export const TitleScene: React.FC<{ scene: TitleSceneType }> = ({
  scene,
}) => {
  const frame = useCurrentFrame();
  const dur = scene.animation?.duration ?? 35;

  const titleOpacity = interpolate(frame, [0, dur], [0, 1], {
    extrapolateRight: "clamp",
  });
  const titleY = interpolate(frame, [0, dur], [50, 0], {
    extrapolateRight: "clamp",
  });

  const subOpacity = interpolate(frame, [Math.floor(dur * 0.6), dur], [0, 1], {
    extrapolateRight: "clamp",
  });
  const subY = interpolate(frame, [Math.floor(dur * 0.6), dur], [20, 0], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill>
      <BackgroundRenderer background={scene.background} />
      <GlowCircle size={700} x={80} y={20} color="#4fc3f7" speed={0.4} />
      <GlowCircle size={500} x={20} y={80} color="#fff" opacity={0.03} speed={0.3} blur={80} />
      <GridOverlay />
      <Vignette />

      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          textAlign: "center",
          width: "85%",
          zIndex: 2,
        }}
      >
        <h1
          style={{
            opacity: titleOpacity,
            transform: `translateY(${titleY}px)`,
            fontSize: 88,
            fontWeight: 800,
            color: "#fff",
            margin: 0,
            lineHeight: 1.25,
            letterSpacing: "3px",
            textShadow: "0 4px 30px rgba(0,0,0,0.5)",
            whiteSpace: "pre-line",
          }}
        >
          {scene.title}
        </h1>

        <DrawLine
          width={100}
          color="#4fc3f7"
          delay={Math.floor(dur * 0.4)}
          duration={18}
          align="center"
          style={{ marginTop: 24, marginBottom: 20 }}
        />

        {scene.subtitle && (
          <p
            style={{
              opacity: subOpacity,
              transform: `translateY(${subY}px)`,
              fontSize: 26,
              color: "#8ab4d6",
              margin: 0,
              letterSpacing: "2px",
              fontWeight: 400,
              textShadow: "0 2px 12px rgba(0,0,0,0.3)",
            }}
          >
            {scene.subtitle}
          </p>
        )}
      </div>
    </AbsoluteFill>
  );
};
