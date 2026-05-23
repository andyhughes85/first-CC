import { AbsoluteFill, Sequence, staticFile } from "remotion";
import { Audio } from "@remotion/media";
import { script } from "./content/script";
import type { Scene } from "./types";
import { TitleScene } from "./scenes/TitleScene";
import { BulletScene } from "./scenes/BulletScene";
import { TextScene } from "./scenes/TextScene";
import { OutroScene } from "./scenes/OutroScene";

export const MyVideo: React.FC = () => {
  let currentFrame = 0;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#000",
        fontFamily:
          '"Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif',
      }}
    >
      {script.scenes.map((scene) => {
        const startFrame = currentFrame;
        currentFrame += scene.durationInFrames;

        return (
          <Sequence
            key={scene.id}
            from={startFrame}
            durationInFrames={scene.durationInFrames}
          >
            <SceneRenderer scene={scene} />
            {scene.narration && (
              <Audio
                src={staticFile(`audio/${scene.narration}.mp3`)}
              />
            )}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

const SceneRenderer: React.FC<{ scene: Scene }> = ({ scene }) => {
  switch (scene.type) {
    case "title":
      return <TitleScene scene={scene} />;
    case "bullets":
      return <BulletScene scene={scene} />;
    case "text":
      return <TextScene scene={scene} />;
    case "outro":
      return <OutroScene scene={scene} />;
    default:
      return null;
  }
};
