# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
14_validation_clean.py - Re-validate after adding proper competitive-swing filters.

Adds three things:
  1. Real competitive-swing filter (drop garbage measurements)
  2. Tightened Test 1 output so we see ALL results, not just the tail
  3. Visualization: plot 3 archetypal players' mean paths in 3D
"""

import sys
sys.path.insert(0, "/home/claude")
import pandas as pd
import numpy as np
import importlib.util
spec = importlib.util.spec_from_file_location("pr", "/home/claude/12_path_reconstruction.py")
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)

reconstruct_path = pr.reconstruct_path
sanity_check_path = pr.sanity_check_path


# -------- Stricter competitive-swing filter --------

def filter_real_swings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter out garbage measurements from Statcast's bat tracking. The
    bat_speed=NaN filter alone isn't enough - Statcast records very low
    bat speeds for check swings, tipped pitches, and other obstructed
    measurements that aren't real swing attempts.

    Thresholds based on real MLB swing distributions:
      bat_speed: 40-90 mph (typical 55-80; extremes are wider tail)
      swing_length: 4-12 ft (typical 6-9)
      |attack_angle|: < 45° (typical -10 to +30)
      swing_path_tilt: 10-50° (typical 25-40)
    """
    before = len(df)
    mask = (
        (df["bat_speed"] >= 40) & (df["bat_speed"] <= 90) &
        (df["swing_length"] >= 4) & (df["swing_length"] <= 12) &
        (df["attack_angle"].abs() <= 45) &
        (df["swing_path_tilt"] >= 10) & (df["swing_path_tilt"] <= 50) &
        (df["attack_direction"].abs() <= 60)
    )
    out = df[mask].copy()
    print(f"  Real-swing filter: {before:,} → {len(out):,} "
          f"({100*(before-len(out))/before:.1f}% dropped as garbage)")
    return out


print("Loading 2025 H1 ...")
df = pd.read_parquet("data/raw/statcast_2025_H1.parquet")
df = df[df["bat_speed"].notna() & df["swing_length"].notna()].copy()
needed = ["bat_speed", "swing_length", "attack_angle", "attack_direction",
          "swing_path_tilt", "intercept_ball_minus_batter_pos_x_inches",
          "intercept_ball_minus_batter_pos_y_inches", "plate_z", "stand"]
df = df.dropna(subset=needed).copy()
print(f"After bat_speed.notna(): {len(df):,}")

df = filter_real_swings(df)
df["intercept_z_in"] = df["plate_z"] * 12


# -------- Test 1 redux: geometric correctness, full summary --------
print("\n" + "=" * 72)
print("TEST 1 redux: Geometric correctness on FILTERED swings")
print("=" * 72)

errors_arclen = []
errors_contact = []
errors_attack_angle = []
n_clipped = 0
for _, row in df.iterrows():
    p = reconstruct_path(
        bat_speed_mph=row["bat_speed"], swing_length_ft=row["swing_length"],
        attack_angle_deg=row["attack_angle"], attack_direction_deg=row["attack_direction"],
        swing_path_tilt_deg=row["swing_path_tilt"],
        intercept_x_in=row["intercept_ball_minus_batter_pos_x_inches"],
        intercept_y_in=row["intercept_ball_minus_batter_pos_y_inches"],
        intercept_z_in=row["intercept_z_in"], handedness=row["stand"],
    )
    chk = sanity_check_path(p)
    errors_arclen.append(abs(chk["arc_len_analytic_ft"] - chk["arc_len_swing_length_ft"]))
    errors_contact.append(chk["contact_recovery_err_ft"])
    errors_attack_angle.append(abs(chk["measured_attack_angle_deg"] - row["attack_angle"]))
    if abs(np.sin(np.radians(row["attack_angle"])) /
           max(abs(np.sin(np.radians(row["swing_path_tilt"]))), 1e-6)) > 1.0:
        n_clipped += 1

errors_arclen = np.array(errors_arclen)
errors_contact = np.array(errors_contact)
errors_attack_angle = np.array(errors_attack_angle)

print(f"\n  n = {len(errors_arclen):,} swings")
print(f"  Arc length error:    median {np.median(errors_arclen):.6f} ft, max {errors_arclen.max():.6f}")
print(f"  Contact recovery:    median {np.median(errors_contact):.6f} ft, max {errors_contact.max():.6f}")
print(f"  Attack angle error:")
print(f"    median:  {np.median(errors_attack_angle):.3f}°")
print(f"    p95:     {np.percentile(errors_attack_angle, 95):.3f}°")
print(f"    p99:     {np.percentile(errors_attack_angle, 99):.3f}°")
print(f"    max:     {errors_attack_angle.max():.3f}°")
print(f"    % within 1.0°: {(errors_attack_angle < 1.0).mean()*100:.2f}%")
print(f"    % within 2.0°: {(errors_attack_angle < 2.0).mean()*100:.2f}%")
print(f"    % within 5.0°: {(errors_attack_angle < 5.0).mean()*100:.2f}%")
print(f"  Over-constrained:    {n_clipped:,} ({100*n_clipped/len(df):.2f}%)")


# -------- Test 3 redux: physical plausibility on clean data --------
print("\n" + "=" * 72)
print("TEST 3 redux: Physical plausibility on FILTERED swings")
print("=" * 72)

sample = df.sample(2000, random_state=42)
all_paths = []
for _, row in sample.iterrows():
    p = reconstruct_path(
        bat_speed_mph=row["bat_speed"], swing_length_ft=row["swing_length"],
        attack_angle_deg=row["attack_angle"], attack_direction_deg=row["attack_direction"],
        swing_path_tilt_deg=row["swing_path_tilt"],
        intercept_x_in=row["intercept_ball_minus_batter_pos_x_inches"],
        intercept_y_in=row["intercept_ball_minus_batter_pos_y_inches"],
        intercept_z_in=row["intercept_z_in"], handedness=row["stand"],
    )
    all_paths.append(p.sample(18))
paths_arr = np.array(all_paths)

mins = paths_arr[..., 2].min(axis=1)
maxs = paths_arr[..., 2].max(axis=1)
contact_y = paths_arr[:, 17, 1]

print(f"\n  Path height (vertical Z) across {len(paths_arr)} swings:")
print(f"    Median min: {np.median(mins):.2f} ft   |  Median max: {np.median(maxs):.2f} ft")
print(f"    Below-ground rate (Z<0):  {(mins<0).mean()*100:.2f}%")
print(f"    Above-7ft  rate (Z>7):    {(maxs>7).mean()*100:.2f}%")

print(f"\n  Contact Y (forward from batter):")
print(f"    Median: {np.median(contact_y):.2f} ft")
print(f"    Negative (behind batter): {(contact_y<0).mean()*100:.2f}%")
print(f"    Range: [{contact_y.min():.2f}, {contact_y.max():.2f}]")


# -------- Test 4 redux: within-player consistency on clean data --------
print("\n" + "=" * 72)
print("TEST 4 redux: Within-player path consistency on FILTERED swings")
print("=" * 72)

test_players = {
    "Aaron Judge":      592450,
    "Steven Kwan":      680757,
    "Matt Wallner":     671213,
    "Jo Adell":         666176,
    "Nick Kurtz":       694671,
}

player_mean_paths = {}
for name, mlbam in test_players.items():
    sub = df[df["batter"] == mlbam]
    if len(sub) < 50:
        print(f"\n  {name}: only {len(sub)} swings, skip"); continue
    sub = sub.sample(min(300, len(sub)), random_state=42)
    paths = []
    radii = []
    for _, row in sub.iterrows():
        p = reconstruct_path(
            bat_speed_mph=row["bat_speed"], swing_length_ft=row["swing_length"],
            attack_angle_deg=row["attack_angle"], attack_direction_deg=row["attack_direction"],
            swing_path_tilt_deg=row["swing_path_tilt"],
            intercept_x_in=row["intercept_ball_minus_batter_pos_x_inches"],
            intercept_y_in=row["intercept_ball_minus_batter_pos_y_inches"],
            intercept_z_in=row["intercept_z_in"], handedness=row["stand"],
        )
        paths.append(p.sample(18))
        radii.append(p.radius)
    paths = np.array(paths)
    mean_path = paths.mean(axis=0)
    player_mean_paths[name] = mean_path
    spread = np.linalg.norm(paths - mean_path, axis=2)
    print(f"\n  {name} (n={len(paths)}):")
    print(f"    Mean 3D path spread:    {spread.mean():.3f} ft")
    print(f"    P95 point deviation:    {np.percentile(spread, 95):.3f} ft")
    print(f"    Max point deviation:    {spread.max():.3f} ft")
    print(f"    Radius: {np.mean(radii):.2f} ± {np.std(radii):.2f} ft")


# -------- Visualize the mean paths of these 5 players --------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

fig = plt.figure(figsize=(14, 8))

# 3D view
ax = fig.add_subplot(1, 2, 1, projection="3d")
colors = {"Aaron Judge": "#534AB7", "Steven Kwan": "#D85A30",
          "Matt Wallner": "#1D9E75", "Jo Adell": "#7F77DD",
          "Nick Kurtz": "#B4B2A9"}
for name, mp in player_mean_paths.items():
    ax.plot(mp[:, 0], mp[:, 1], mp[:, 2], color=colors[name], linewidth=2,
            label=name, alpha=0.85)
    ax.scatter(mp[-1, 0], mp[-1, 1], mp[-1, 2], color=colors[name],
               s=100, marker="o", edgecolor="black", zorder=10)
ax.set_xlabel("X (across, ft)")
ax.set_ylabel("Y (toward pitcher, ft)")
ax.set_zlabel("Z (height, ft)")
ax.set_title("Mean 3D bat paths (• = contact)")
ax.legend(fontsize=8, loc="upper left")

# Side view: Y vs Z (the canonical "swing path" view from behind catcher)
ax2 = fig.add_subplot(1, 2, 2)
for name, mp in player_mean_paths.items():
    ax2.plot(mp[:, 1], mp[:, 2], color=colors[name], linewidth=2.5,
             label=name, alpha=0.85)
    ax2.scatter(mp[-1, 1], mp[-1, 2], color=colors[name], s=100,
                marker="o", edgecolor="black", zorder=10)
    ax2.scatter(mp[0, 1], mp[0, 2], color=colors[name], s=60,
                marker="s", edgecolor="black", zorder=10)
ax2.set_xlabel("Y - toward pitcher (ft)")
ax2.set_ylabel("Z - height (ft)")
ax2.set_title("Side view (■ = swing start, • = contact)")
ax2.legend(fontsize=9)
ax2.grid(True, alpha=0.3)
ax2.axhline(y=0, color="brown", linewidth=1, alpha=0.4, linestyle="--",
            label="ground")
ax2.set_ylim(0, 6)

plt.tight_layout()
out_path = "/mnt/user-data/outputs/swing_paths_5_players.png"
plt.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"\nSaved visualization: {out_path}")
