import React from "react";
import { AbsoluteFill } from "remotion";
import type { Background } from "../types";

export const BackgroundRenderer: React.FC<{
  background: Background;
}> = ({ background }) => {
  if (background.type === "gradient") {
    return (
      <AbsoluteFill
        style={{
          background: `linear-gradient(${background.direction ?? 135}deg, ${
            background.colors?.[0] ?? "#000"
          }, ${background.colors?.[1] ?? "#333"})`,
        }}
      />
    );
  }

  return (
    <AbsoluteFill
      style={{
        backgroundColor: background.color ?? "#1a1a2e",
      }}
    />
  );
};
