# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""16_visualize_2d.py - Show the 2D mean paths for sanity check."""

import sys
sys.path.insert(0, "/home/claude")
import numpy as np
import pandas as pd
import importlib.util
spec = importlib.util.spec_from_file_location("p2d", "/home/claude/15_path_2d.py")
p2d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p2d)
reconstruct_path_2d = p2d.reconstruct_path_2d

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

df = pd.read_parquet("data/raw/statcast_2025_H1.parquet")
df = df[df["bat_speed"].notna() & df["swing_length"].notna()].copy()
needed = ["bat_speed", "swing_length", "attack_angle",
          "intercept_ball_minus_batter_pos_y_inches", "plate_z"]
df = df.dropna(subset=needed)
mask = (
    (df["bat_speed"] >= 40) & (df["bat_speed"] <= 90) &
    (df["swing_length"] >= 4) & (df["swing_length"] <= 12) &
    (df["attack_angle"].abs() <= 45)
)
df = df[mask].copy()
df["intercept_z_in"] = df["plate_z"] * 12

players = {
    "Aaron Judge":  (592450, "#534AB7"),
    "Steven Kwan":  (680757, "#D85A30"),
    "Matt Wallner": (671213, "#1D9E75"),
    "Jo Adell":     (666176, "#7F77DD"),
    "Nick Kurtz":   (694671, "#222222"),
}

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

# Left: mean paths
all_paths = {}
for name, (mlbam, color) in players.items():
    sub = df[df["batter"] == mlbam]
    if len(sub) < 50:
        continue
    sub = sub.sample(min(300, len(sub)), random_state=42)
    paths = []
    for _, row in sub.iterrows():
        p = reconstruct_path_2d(
            attack_angle_deg=row["attack_angle"],
            swing_length_ft=row["swing_length"],
            intercept_y_in=row["intercept_ball_minus_batter_pos_y_inches"],
            intercept_z_in=row["intercept_z_in"],
            bat_speed_mph=row["bat_speed"],
        )
        paths.append(p.sample(18))
    paths = np.array(paths)
    mean_path = paths.mean(axis=0)
    std_path = paths.std(axis=0)
    all_paths[name] = (mean_path, std_path, paths, color)

    ax1.plot(mean_path[:, 0], mean_path[:, 1], color=color, linewidth=3,
             label=f"{name}", alpha=0.9)
    ax1.scatter(mean_path[0, 0], mean_path[0, 1], color=color, s=80,
                marker="s", edgecolor="black", zorder=10)
    ax1.scatter(mean_path[-1, 0], mean_path[-1, 1], color=color, s=100,
                marker="o", edgecolor="black", zorder=10)

ax1.set_xlabel("Y - distance from batter toward pitcher (ft)")
ax1.set_ylabel("Z - height above ground (ft)")
ax1.set_title("Mean 2D bat paths (side view)\n■ = swing start, ● = contact")
ax1.legend(fontsize=10, loc="upper left")
ax1.grid(True, alpha=0.3)
ax1.axhline(y=0, color="brown", linewidth=1.5, alpha=0.5, linestyle="--")
ax1.set_xlim(-5, 5)
ax1.set_ylim(0, 7)
ax1.set_aspect("equal")

# Right: individual swings for Judge to show within-player spread
name = "Aaron Judge"
mean_path, _, paths, color = all_paths[name]
# Sample 30 paths
indices = np.random.RandomState(42).choice(len(paths), 30, replace=False)
for i in indices:
    ax2.plot(paths[i, :, 0], paths[i, :, 1], color=color, alpha=0.15, linewidth=1)
ax2.plot(mean_path[:, 0], mean_path[:, 1], color=color, linewidth=3.5, alpha=1.0,
         label=f"{name} mean (n=300)")
ax2.scatter(mean_path[-1, 0], mean_path[-1, 1], color=color, s=120,
            marker="o", edgecolor="black", zorder=10)
ax2.set_xlabel("Y - distance from batter toward pitcher (ft)")
ax2.set_ylabel("Z - height above ground (ft)")
ax2.set_title(f"Individual swing variation: Aaron Judge\n(30 random swings + mean)")
ax2.legend(fontsize=10, loc="upper left")
ax2.grid(True, alpha=0.3)
ax2.axhline(y=0, color="brown", linewidth=1.5, alpha=0.5, linestyle="--")
ax2.set_xlim(-5, 5)
ax2.set_ylim(0, 7)
ax2.set_aspect("equal")

plt.tight_layout()
out = "/mnt/user-data/outputs/swing_paths_2d.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"Saved: {out}")
