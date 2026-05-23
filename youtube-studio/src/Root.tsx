import { Composition } from "remotion";
import { MyVideo } from "./Video";
import { script } from "./content/script";

export const Root: React.FC = () => {
  const totalFrames = script.scenes.reduce(
    (acc, scene) => acc + scene.durationInFrames,
    0,
  );

  return (
    <Composition
      id="MainVideo"
      component={MyVideo}
      durationInFrames={totalFrames}
      fps={script.fps}
      width={script.width}
      height={script.height}
    />
  );
};
