# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
13_path_validation.py - Comprehensive sanity checks on the path reconstruction.

Tests, in order:
  1. Geometric correctness: arc length, contact recovery, attack angle
     recovery, tangent unit length on every swing in a real sample.
  2. Edge cases: extreme attack angles (Kwan-flat, Cal Raleigh-steep),
     unusual swing lengths, contact-point extremes.
  3. Over-constraint diagnosis: how often does the attack-angle vs tilt
     mismatch require clipping? How big are the clipping errors?
  4. Physical plausibility: do the reconstructed paths actually live where
     swings should be in 3D space? (e.g., the bat shouldn't be 10 feet
     above the ground at any point in the swing.)
  5. Player-level consistency: do all swings by one player produce paths
     that look like one another? (high within-player consistency = stable
     features; chaos = our model is too sensitive to noise.)
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

# Load a meaningful sample - 2025 H1 only, for speed
print("Loading 2025 H1 competitive swings for validation...")
df = pd.read_parquet("data/raw/statcast_2025_H1.parquet")
df = df[df["bat_speed"].notna() & df["swing_length"].notna()].copy()

# Required fields - drop any with missing
needed = ["bat_speed", "swing_length", "attack_angle", "attack_direction",
          "swing_path_tilt", "intercept_ball_minus_batter_pos_x_inches",
          "intercept_ball_minus_batter_pos_y_inches", "plate_z", "stand"]
df = df.dropna(subset=needed).copy()

# We need intercept_z too. Statcast doesn't expose it cleanly in pybaseball
# output - use plate_z as a reasonable proxy (the height at which the
# pitch crossed the plate, which is near where bat-ball contact occurs).
# This is an approximation: actual contact height can differ from plate_z
# by a few inches depending on where in front of the plate the bat reaches
# the ball. Document this clearly.
df["intercept_z_in"] = df["plate_z"] * 12  # plate_z is in feet

print(f"Validation sample: {len(df):,} swings")


# ============================================================
# TEST 1: Geometric correctness on every swing
# ============================================================
print("\n" + "=" * 72)
print("TEST 1: Geometric correctness across all swings")
print("=" * 72)

errors_arclen = []
errors_contact = []
errors_attack_angle = []
errors_tangent_unit = []
n_clipped = 0

for _, row in df.iterrows():
    try:
        p = reconstruct_path(
            bat_speed_mph=row["bat_speed"],
            swing_length_ft=row["swing_length"],
            attack_angle_deg=row["attack_angle"],
            attack_direction_deg=row["attack_direction"],
            swing_path_tilt_deg=row["swing_path_tilt"],
            intercept_x_in=row["intercept_ball_minus_batter_pos_x_inches"],
            intercept_y_in=row["intercept_ball_minus_batter_pos_y_inches"],
            intercept_z_in=row["intercept_z_in"],
            handedness=row["stand"],
        )
        chk = sanity_check_path(p)
        errors_arclen.append(abs(chk["arc_len_analytic_ft"] - chk["arc_len_swing_length_ft"]))
        errors_contact.append(chk["contact_recovery_err_ft"])
        # Note: for LHH, we mirrored X, but attack_angle (vertical) shouldn't
        # change sign. So the recovered angle's sign should match input.
        recovered_aa = chk["measured_attack_angle_deg"]
        errors_attack_angle.append(abs(recovered_aa - row["attack_angle"]))
        # Tangent should be unit length
        t = p.tangent_at(1.0)
        errors_tangent_unit.append(abs(np.linalg.norm(t) - 1.0))
        # Detect clipping: when sin(aa)/sin(tilt) > 1
        if abs(np.sin(np.radians(row["attack_angle"])) /
               max(abs(np.sin(np.radians(row["swing_path_tilt"]))), 1e-6)) > 1.0:
            n_clipped += 1
    except Exception as e:
        print(f"  FAILED on row: {e}")
        continue

errors_arclen = np.array(errors_arclen)
errors_contact = np.array(errors_contact)
errors_attack_angle = np.array(errors_attack_angle)
errors_tangent_unit = np.array(errors_tangent_unit)

def summarize(name, errs, unit, tol):
    p50 = np.percentile(errs, 50)
    p95 = np.percentile(errs, 95)
    p99 = np.percentile(errs, 99)
    pmax = errs.max()
    pass_frac = (errs < tol).mean() * 100
    print(f"\n  {name}:")
    print(f"    median: {p50:.5f} {unit}    p95: {p95:.5f}    p99: {p99:.5f}    max: {pmax:.5f}")
    print(f"    pct within {tol} {unit}: {pass_frac:.2f}%")

summarize("Arc length error", errors_arclen, "ft", 0.001)
summarize("Contact recovery error", errors_contact, "ft", 0.001)
summarize("Attack angle error", errors_attack_angle, "deg", 0.5)
summarize("Tangent unit-norm error", errors_tangent_unit, "n/a", 1e-6)

print(f"\n  Over-constrained swings (would need clipping): "
      f"{n_clipped:,} ({100*n_clipped/len(df):.1f}%)")


# ============================================================
# TEST 2: Extreme value swings
# ============================================================
print("\n" + "=" * 72)
print("TEST 2: Edge cases - extreme attack angles and swing lengths")
print("=" * 72)

# Pull extremes
def show_extreme(label, sub):
    """Reconstruct one row from sub and report the path summary."""
    if len(sub) == 0:
        print(f"  {label}: no rows match")
        return
    row = sub.iloc[0]
    p = reconstruct_path(
        bat_speed_mph=row["bat_speed"],
        swing_length_ft=row["swing_length"],
        attack_angle_deg=row["attack_angle"],
        attack_direction_deg=row["attack_direction"],
        swing_path_tilt_deg=row["swing_path_tilt"],
        intercept_x_in=row["intercept_ball_minus_batter_pos_x_inches"],
        intercept_y_in=row["intercept_ball_minus_batter_pos_y_inches"],
        intercept_z_in=row["intercept_z_in"],
        handedness=row["stand"],
    )
    pts = p.sample(18)
    chk = sanity_check_path(p)
    print(f"\n  {label}")
    print(f"    Inputs: bs={row['bat_speed']:.1f} mph, sl={row['swing_length']:.2f} ft,")
    print(f"            aa={row['attack_angle']:.1f}°, ad={row['attack_direction']:.1f}°, tilt={row['swing_path_tilt']:.1f}°")
    print(f"    Radius: {p.radius:.2f} ft, recovered aa: {chk['measured_attack_angle_deg']:.2f}°")
    print(f"    Path start  Z (height ft): {pts[0][2]:+.2f}")
    print(f"    Path middle Z: {pts[9][2]:+.2f}")
    print(f"    Path contact Z: {pts[17][2]:+.2f}")
    print(f"    Min path height: {pts[:,2].min():+.2f}, Max: {pts[:,2].max():+.2f}")

show_extreme("Most negative attack angle (steepest down)",
             df.nsmallest(1, "attack_angle"))
show_extreme("Most positive attack angle (steepest up)",
             df.nlargest(1, "attack_angle"))
show_extreme("Shortest swing length",
             df.nsmallest(1, "swing_length"))
show_extreme("Longest swing length",
             df.nlargest(1, "swing_length"))
show_extreme("Slowest bat speed",
             df.nsmallest(1, "bat_speed"))
show_extreme("Fastest bat speed",
             df.nlargest(1, "bat_speed"))


# ============================================================
# TEST 3: Physical plausibility
# ============================================================
print("\n" + "=" * 72)
print("TEST 3: Physical plausibility of reconstructed paths")
print("=" * 72)
print("Sampling 18 points per swing on a 1000-swing random subsample.")
print("Checking: path heights in reasonable range, no NaN/inf, contact")
print("forward of the plate, start point behind/above contact.")

sample = df.sample(1000, random_state=42)
min_heights = []
max_heights = []
contact_y = []
start_relative_to_contact = []

for _, row in sample.iterrows():
    p = reconstruct_path(
        bat_speed_mph=row["bat_speed"],
        swing_length_ft=row["swing_length"],
        attack_angle_deg=row["attack_angle"],
        attack_direction_deg=row["attack_direction"],
        swing_path_tilt_deg=row["swing_path_tilt"],
        intercept_x_in=row["intercept_ball_minus_batter_pos_x_inches"],
        intercept_y_in=row["intercept_ball_minus_batter_pos_y_inches"],
        intercept_z_in=row["intercept_z_in"],
        handedness=row["stand"],
    )
    pts = p.sample(18)
    if np.any(np.isnan(pts)) or np.any(np.isinf(pts)):
        print(f"  WARNING: NaN/inf detected for row {row.name}")
        continue
    min_heights.append(pts[:, 2].min())
    max_heights.append(pts[:, 2].max())
    contact_y.append(pts[17, 1])  # Y = toward pitcher
    # Vector from contact to start in 3D
    start_relative_to_contact.append(pts[0] - pts[17])

min_heights = np.array(min_heights)
max_heights = np.array(max_heights)
contact_y = np.array(contact_y)
start_rel = np.array(start_relative_to_contact)

print(f"\n  Path height ranges across {len(min_heights)} swings:")
print(f"    Min height observed: {min_heights.min():.2f} ft (should be > 0 always)")
print(f"    Max height observed: {max_heights.max():.2f} ft (should be < 8 - bat path doesn't exceed reasonable swing height)")
print(f"    Median (min, max):   ({np.median(min_heights):.2f}, {np.median(max_heights):.2f}) ft")
print(f"    Fraction with min height < 0 (below ground!): "
      f"{(min_heights < 0).mean() * 100:.2f}%")
print(f"    Fraction with max height > 7 ft: "
      f"{(max_heights > 7).mean() * 100:.2f}%")

print(f"\n  Contact Y (forward distance from batter):")
print(f"    Median: {np.median(contact_y):.2f} ft")
print(f"    Range:  [{contact_y.min():.2f}, {contact_y.max():.2f}] ft")
print(f"    (Should be positive — contact happens in front of batter.")
print(f"     Negative values would indicate the bat met the ball behind the batter, which is unphysical.)")

print(f"\n  Path start position relative to contact:")
print(f"    Median start - contact displacement (ft):")
print(f"      X (across):    {np.median(start_rel[:, 0]):+.2f}")
print(f"      Y (back/fwd):  {np.median(start_rel[:, 1]):+.2f}")
print(f"      Z (vertical):  {np.median(start_rel[:, 2]):+.2f}")
print(f"    (Expected: start should be BACK (negative Y) and slightly")
print(f"     above contact (positive Z) - the typical 'loaded' position.")
print(f"     X direction depends on swing direction.)")


# ============================================================
# TEST 4: Player-level consistency
# ============================================================
print("\n" + "=" * 72)
print("TEST 4: Within-player path consistency")
print("=" * 72)
print("For known players, reconstruct ALL their 2025 H1 paths and measure")
print("how variable the resulting paths are. Same player = similar paths?")

# Player IDs from earlier conversation
test_players = {
    "Aaron Judge":      592450,
    "Steven Kwan":      680757,
    "Matt Wallner":     671213,
    "Jo Adell":         666176,
    "Nick Kurtz":       694671,  # may or may not be in our data
}

for name, mlbam in test_players.items():
    sub = df[df["batter"] == mlbam]
    if len(sub) < 50:
        print(f"\n  {name} (id={mlbam}): only {len(sub)} swings, skip")
        continue
    sub = sub.sample(min(200, len(sub)), random_state=42)
    paths = []
    for _, row in sub.iterrows():
        p = reconstruct_path(
            bat_speed_mph=row["bat_speed"],
            swing_length_ft=row["swing_length"],
            attack_angle_deg=row["attack_angle"],
            attack_direction_deg=row["attack_direction"],
            swing_path_tilt_deg=row["swing_path_tilt"],
            intercept_x_in=row["intercept_ball_minus_batter_pos_x_inches"],
            intercept_y_in=row["intercept_ball_minus_batter_pos_y_inches"],
            intercept_z_in=row["intercept_z_in"],
            handedness=row["stand"],
        )
        paths.append(p.sample(18))
    paths = np.array(paths)  # (n_swings, 18, 3)

    # Mean path and within-player spread
    mean_path = paths.mean(axis=0)
    spread = np.linalg.norm(paths - mean_path, axis=2)  # (n_swings, 18) - 3D euclid
    # Average spread across points and swings
    mean_spread = spread.mean()
    max_spread = spread.max()

    # Radius variability (the single most important shape param)
    radii = np.array([np.linalg.norm(p[0] - p.mean(axis=0)) for p in paths])  # crude proxy
    print(f"\n  {name} ({len(sub)} swings):")
    print(f"    Mean 3D path spread (avg dist to mean path):  {mean_spread:.3f} ft")
    print(f"    Max  3D point deviation from mean:            {max_spread:.3f} ft")
    print(f"    Mean radius across swings: {radii.mean():.2f} ± {radii.std():.2f} ft")
