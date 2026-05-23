import type { VideoScript } from "../types";

export const script: VideoScript = {
  title: "The Portfolio That Believes in Nothing",
  fps: 30,
  width: 1920,
  height: 1080,
  scenes: [
    {
      id: "title",
      type: "title",
      durationInFrames: 120,
      title: "The Portfolio That\nBelieves in Nothing",
      subtitle: "Two Sigma — $123.9 Billion of Radical Humility",
      background: {
        type: "gradient",
        colors: ["#0a0e1a", "#1a2744", "#0d1b2a"],
        direction: 135,
      },
      animation: { enter: "scale", duration: 40 },
    },
    {
      id: "hook",
      type: "text",
      durationInFrames: 420,
      bodyText:
        "What if I told you the most unshakeable portfolio on Earth... doesn't believe in anything?\n\nThis isn't diversification. This is the mathematical elimination of belief.",
      background: { type: "solid", color: "#0a0e1a" },
      animation: { enter: "fade", duration: 20 },
      narration: "hook",
    },
    {
      id: "the-numbers",
      type: "bullets",
      durationInFrames: 480,
      title: "$123.9 Billion",
      bullets: [
        "3,742 positions",
        "No center",
        "No anchor",
        "No narrative",
      ],
      background: {
        type: "gradient",
        colors: ["#0a0e1a", "#1a2744"],
        direction: 180,
      },
      animation: { enter: "fade", duration: 15 },
      narration: "the-numbers",
    },
    {
      id: "probability-field",
      type: "text",
      durationInFrames: 390,
      title: "A Probability Field",
      bodyText:
        "This is not a portfolio.\nIt is a probability field.\nA system that no longer selects outcomes...\nbut samples state space itself.",
      background: { type: "solid", color: "#0d1b2a" },
      animation: { enter: "fade", duration: 20 },
      narration: "probability-field",
    },
    {
      id: "jun",
      type: "text",
      durationInFrames: 480,
      title: "Jūn — 均衡",
      bodyText:
        "The ancient text of Liezi calls this Jūn — absolute equilibrium.\n\nWhen balance reaches its extreme... nothing can be broken.\nThis portfolio is that equilibrium made visible.",
      background: {
        type: "gradient",
        colors: ["#0a0e1a", "#1b2838"],
        direction: 135,
      },
      animation: { enter: "fade", duration: 20 },
      narration: "jun",
    },
    {
      id: "the-masters",
      type: "bullets",
      durationInFrames: 900,
      title: "The Intellectual Framework",
      bullets: [
        "Graham: safety is not a margin — it is the architecture",
        "Dalio: 15+ uncorrelated bets to cancel out luck",
        "Naval: a system that wins 999/1000 parallel universes",
        "That is ergodic survival",
      ],
      background: {
        type: "gradient",
        colors: ["#0a0e1a", "#1a2744", "#0a0e1a"],
        direction: 180,
      },
      animation: { enter: "fade", duration: 15 },
      narration: "the-masters",
    },
    {
      id: "non-ergodic",
      type: "text",
      durationInFrames: 420,
      title: "Non-Ergodic Ruin",
      bodyText:
        "Concentrated capital faces non-ergodic ruin.\nA single path, no matter how brilliant, can break.\nOne fatal misstep... and you are zero.",
      background: { type: "solid", color: "#1a0a0a" },
      animation: { enter: "fade", duration: 20 },
      narration: "non-ergodic",
    },
    {
      id: "delete-ego",
      type: "text",
      durationInFrames: 450,
      bodyText:
        "To delete conviction... is to delete the ego.\n\nGraham warned: the investor's chief enemy... is himself.\nAt this scale... human arrogance has nowhere to land.",
      background: {
        type: "gradient",
        colors: ["#0a0e1a", "#1b2838"],
        direction: 135,
      },
      animation: { enter: "fade", duration: 20 },
      narration: "delete-ego",
    },
    {
      id: "laozi",
      type: "text",
      durationInFrames: 360,
      title: "Laozi — 道德经",
      bodyText:
        "Thirty spokes share one hub.\nIt is the empty space within that gives the wheel its use.\n\nThis architecture is that emptiness.",
      background: {
        type: "gradient",
        colors: ["#0a0e1a", "#0d2137", "#0a0e1a"],
        direction: 135,
      },
      animation: { enter: "fade", duration: 25 },
      narration: "laozi",
    },
    {
      id: "zhuangzi",
      type: "text",
      durationInFrames: 540,
      title: "Zhuangzi — 庄子",
      bodyText:
        "The perfect mind is a mirror.\nIt responds... but does not retain.\n\nLike water... it fills every micro-crack of inefficiency.\nIt does not choose the container.\nIt becomes the shape.",
      background: { type: "solid", color: "#0a0e1a" },
      animation: { enter: "fade", duration: 20 },
      narration: "zhuangzi",
    },
    {
      id: "the-question",
      type: "text",
      durationInFrames: 540,
      bodyText:
        "The question is no longer: what do I believe?\n\nBut instead: what can survive being wrong everywhere?\n\nA concentrated mind tries to be right.\nA distributed system tries to break less.",
      background: {
        type: "gradient",
        colors: ["#0a0e1a", "#1a2744"],
        direction: 135,
      },
      animation: { enter: "fade", duration: 25 },
      narration: "the-question",
    },
    {
      id: "outro",
      type: "outro",
      durationInFrames: 150,
      title: "The Tao of Investing",
      subtitle: "If you think in systems... not stories... subscribe.",
      brandText: "Stay shapeless.",
      background: {
        type: "gradient",
        colors: ["#0a0e1a", "#1a2744", "#0d1b2a"],
        direction: 135,
      },
      animation: { enter: "scale", duration: 30 },
    },
  ],
};
