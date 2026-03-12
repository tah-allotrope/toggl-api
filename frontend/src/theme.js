export const COLORS = {
  bg: "#0a0a1a",
  bg2: "#12122a",
  bg3: "#1a1a3e",
  cyan: "#00fff9",
  magenta: "#ff00ff",
  green: "#39ff14",
  purple: "#bc13fe",
  pink: "#ff2079",
  gold: "#ffd700",
  amber: "#ff9800",
  red: "#ff3131",
  text: "#e0e0ff",
  textMuted: "#7878a8",
  grid: "#1e1e4a",
  border: "#2a2a5a"
};

export const NEON_SEQUENCE = [
  COLORS.cyan,
  COLORS.magenta,
  COLORS.green,
  COLORS.purple,
  COLORS.pink,
  COLORS.gold,
  COLORS.amber,
  COLORS.red,
  "#00b4d8",
  "#e040fb",
  "#76ff03",
  "#7c4dff",
  "#18ffff",
  "#ff6e40",
  "#eeff41",
  "#ea80fc"
];

export const SCALE_CYAN_MAGENTA = [
  [0.0, "#0a0a1a"],
  [0.2, "#0d2d5e"],
  [0.4, "#1a5276"],
  [0.6, "#00b4d8"],
  [0.8, "#00fff9"],
  [1.0, "#ff00ff"]
];

export const SCALE_NEON_HEATMAP = [
  [0.0, "#0a0a1a"],
  [0.15, "#0d1b3e"],
  [0.3, "#0d3d6b"],
  [0.5, "#00778a"],
  [0.7, "#00c9b7"],
  [0.85, "#00fff9"],
  [1.0, "#39ff14"]
];

export const SCALE_MAGENTA_FIRE = [
  [0.0, "#0a0a1a"],
  [0.25, "#3d0a5e"],
  [0.5, "#8a0e7b"],
  [0.75, "#ff00ff"],
  [1.0, "#ff2079"]
];

export const SCALE_CYAN_MONO = [
  [0.0, "#0a0a1a"],
  [0.25, "#0a2a3a"],
  [0.5, "#0d5e7a"],
  [0.75, "#00b4d8"],
  [1.0, "#00fff9"]
];

export const SCALE_PURPLE_GOLD = [
  [0.0, "#0a0a1a"],
  [0.25, "#2a0a5e"],
  [0.5, "#bc13fe"],
  [0.75, "#ff9800"],
  [1.0, "#ffd700"]
];

export const PLOTLY_LAYOUT = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(10,10,26,0.6)",
  font: {
    family: "Share Tech Mono, monospace",
    color: COLORS.text,
    size: 12
  },
  xaxis: {
    gridcolor: COLORS.grid,
    linecolor: COLORS.border,
    zerolinecolor: COLORS.border,
    tickfont: { color: COLORS.textMuted },
    title: { font: { color: COLORS.textMuted } }
  },
  yaxis: {
    gridcolor: COLORS.grid,
    linecolor: COLORS.border,
    zerolinecolor: COLORS.border,
    tickfont: { color: COLORS.textMuted },
    title: { font: { color: COLORS.textMuted } }
  },
  legend: {
    bgcolor: "rgba(0,0,0,0)",
    font: { color: COLORS.textMuted },
    bordercolor: COLORS.border,
    borderwidth: 1
  },
  colorway: NEON_SEQUENCE,
  hoverlabel: {
    bgcolor: COLORS.bg2,
    bordercolor: COLORS.cyan,
    font: {
      color: COLORS.text,
      family: "Share Tech Mono, monospace"
    }
  },
  margin: { l: 20, r: 20, t: 40, b: 20 }
};
