/** 背景配置 */
export interface Background {
  type: "solid" | "gradient";
  color?: string;
  colors?: string[];
  direction?: number;
}

/** 动画配置 */
export interface Animation {
  enter: "fade" | "slideUp" | "slideLeft" | "scale" | "none";
  duration?: number;
}

/** 场景基类 */
interface SceneBase {
  id: string;
  durationInFrames: number;
  background: Background;
  animation?: Partial<Animation>;
  narration?: string; // 对应 public/audio/{id}.mp3
}

/** 标题场景 */
export interface TitleScene extends SceneBase {
  type: "title";
  title: string;
  subtitle?: string;
}

/** 要点列表场景 */
export interface BulletScene extends SceneBase {
  type: "bullets";
  title?: string;
  bullets: string[];
}

/** 正文场景 */
export interface TextScene extends SceneBase {
  type: "text";
  title?: string;
  bodyText: string;
}

/** 结尾场景 */
export interface OutroScene extends SceneBase {
  type: "outro";
  title: string;
  subtitle?: string;
  brandText?: string;
}

export type Scene = TitleScene | BulletScene | TextScene | OutroScene;

/** 完整视频脚本 */
export interface VideoScript {
  title: string;
  fps: number;
  width: number;
  height: number;
  scenes: Scene[];
}
