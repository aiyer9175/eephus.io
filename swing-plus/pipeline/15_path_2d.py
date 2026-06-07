# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
15_path_2d.py - 2D side-view bat path reconstruction.

Geometry:
  - Work in the (Y, Z) plane: Y = depth toward pitcher, Z = vertical height.
  - Contact point: (intercept_y, intercept_z) in feet.
  - Tangent at contact: angle = attack_angle (degrees, + up).
  - Path: circular arc, radius = swing_length / sweep_angle_rad.
  - Center: perpendicular to tangent, on concave side.

What we deliberately give up vs. the 3D version:
  - attack_direction (pull/push): not represented in this view
  - swing_path_tilt: not represented (it's a 3D plane angle)
  - intercept_x: not represented

These can still enter the downstream model as features, but they don't
affect path reconstruction. The simplification is that we're representing
the VERTICAL swing profile only, which is what coaches mean when they say
"his bat path is too steep" or "he's not on plane through the zone".
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass


# Default sweep angle for the circular arc (in degrees)
# Same value as our 3D version - controls how much of the implied swing
# is represented by the reconstructed arc. 100° is roughly the angular
# range over which scouts care about path quality.
DEFAULT_SWEEP_DEG = 100.0
DEG = np.pi / 180.0
FT_PER_INCH = 1.0 / 12.0


@dataclass
class SwingPath2D:
    """2D parametric representation of a bat path in the (Y, Z) side view."""
    center_yz: np.ndarray   # (2,) circle center in 2D
    radius: float           # arc radius (ft)
    theta_start: float      # starting angle on the circle (radians)
    theta_contact: float    # ending angle (at contact, radians)
    contact_yz: np.ndarray  # (2,) where the bat met the ball

    # Pass-through diagnostics
    attack_angle_deg: float
    swing_length_ft: float
    bat_speed_mph: float

    def position_at(self, t: float) -> np.ndarray:
        """2D position at parameter t in [0, 1] along the path."""
        theta = self.theta_start + t * (self.theta_contact - self.theta_start)
        return self.center_yz + self.radius * np.array([np.cos(theta), np.sin(theta)])

    def sample(self, n: int = 18) -> np.ndarray:
        """Return (n, 2) array of 2D points along the path."""
        ts = np.linspace(0, 1, n)
        return np.array([self.position_at(t) for t in ts])

    def tangent_at(self, t: float) -> np.ndarray:
        """Unit tangent vector at parameter t (direction of motion)."""
        theta = self.theta_start + t * (self.theta_contact - self.theta_start)
        # Standard CCW: position derivative w.r.t. theta = (-sin θ, cos θ)
        tangent = np.array([-np.sin(theta), np.cos(theta)])
        return tangent / np.linalg.norm(tangent)

    def bat_angle_at(self, t: float) -> float:
        """Vertical angle of the bat's velocity in degrees (+ up)."""
        tangent = self.tangent_at(t)
        return np.degrees(np.arctan2(tangent[1], tangent[0]))


def reconstruct_path_2d(
    attack_angle_deg: float,
    swing_length_ft: float,
    intercept_y_in: float,
    intercept_z_in: float,
    bat_speed_mph: float = 0.0,
    sweep_deg: float = DEFAULT_SWEEP_DEG,
) -> SwingPath2D:
    """
    Build a 2D side-view path from contact-point measurements.

    The geometry is fully determined by 4 inputs:
      attack_angle: tangent direction at contact
      swing_length: arc length
      intercept_y, intercept_z: 2D contact location

    No conventions to reconcile, no plane to rotate, no signs to flip.
    """
    sweep_rad = sweep_deg * DEG
    R = swing_length_ft / sweep_rad

    alpha = attack_angle_deg * DEG
    sin_a, cos_a = np.sin(alpha), np.cos(alpha)

    # Contact point in 2D
    contact_yz = np.array([
        intercept_y_in * FT_PER_INCH,
        intercept_z_in * FT_PER_INCH,
    ])

    # Tangent at contact: (cos α, sin α)
    # For a circle with center C and the bat moving CCW, the tangent at
    # a point P on the circle is perpendicular to the radius (C → P),
    # rotated 90° CCW. Equivalently: the inward normal (pointing toward
    # center) is the tangent rotated 90° CCW: (-sin α, cos α).
    inward = np.array([-sin_a, cos_a])
    center_yz = contact_yz + R * inward

    # The angle of the contact point on the circle (measured from center):
    # vector from center to contact = -R * inward = R * (sin α, -cos α)
    # So contact is at angle θ_c where (cos θ_c, sin θ_c) = (sin α, -cos α)
    # → θ_c = arctan2(-cos α, sin α)
    theta_contact = np.arctan2(-cos_a, sin_a)

    # Bat sweeps CCW from theta_start to theta_contact
    theta_start = theta_contact - sweep_rad

    return SwingPath2D(
        center_yz=center_yz,
        radius=R,
        theta_start=theta_start,
        theta_contact=theta_contact,
        contact_yz=contact_yz,
        attack_angle_deg=attack_angle_deg,
        swing_length_ft=swing_length_ft,
        bat_speed_mph=bat_speed_mph,
    )


# ==================================================================
# Validation 1: Bare-metal geometric sanity on a few archetypal swings
# ==================================================================

if __name__ == "__main__":
    print("=" * 72)
    print("VALIDATION 1: Single-swing geometric correctness")
    print("=" * 72)

    test_cases = [
        # (name, attack_angle, swing_length, intercept_y_in, intercept_z_in)
        ("Aaron Judge avg",      13.4, 7.92, 33.0, 35.0),
        ("Steven Kwan avg",       2.1, 7.05, 28.0, 33.0),
        ("Matt Wallner avg",     11.4, 7.32, 36.3, 34.0),
        ("Jo Adell avg",          7.8, 7.71, 26.0, 33.0),
        ("Cal Raleigh (steep)",  17.3, 7.50, 30.0, 34.0),
        ("Vlad Jr (flat)",        3.0, 7.20, 32.0, 33.0),
        ("Extreme downswing",   -10.0, 7.00, 30.0, 28.0),
        ("Extreme upswing",      28.0, 7.50, 32.0, 36.0),
    ]

    print(f"\n{'Name':<25}{'AA in':>8}{'AA out':>10}{'AA err':>9}{'R (ft)':>10}{'Arc len':>10}")
    print("-" * 75)

    for name, aa, sl, iy, iz in test_cases:
        path = reconstruct_path_2d(aa, sl, iy, iz)
        # Recover attack angle from tangent at contact
        aa_recovered = path.bat_angle_at(1.0)
        aa_err = abs(aa_recovered - aa)
        # Verify arc length numerically
        pts = path.sample(100)
        arc_len_numeric = np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()
        # Verify contact point recovered
        contact_recovered = path.position_at(1.0)
        contact_err = np.linalg.norm(contact_recovered - path.contact_yz)
        print(f"{name:<25}{aa:>8.2f}{aa_recovered:>10.2f}{aa_err:>9.3f}{path.radius:>10.3f}{arc_len_numeric:>10.3f}")

    # ==================================================================
    # Validation 2: All-up geometric correctness on real data
    # ==================================================================
    print("\n" + "=" * 72)
    print("VALIDATION 2: Geometric correctness on real Statcast 2025 H1")
    print("=" * 72)

    df = pd.read_parquet("data/raw/statcast_2025_H1.parquet")
    df = df[df["bat_speed"].notna() & df["swing_length"].notna()].copy()
    needed = ["bat_speed", "swing_length", "attack_angle",
              "intercept_ball_minus_batter_pos_y_inches", "plate_z"]
    df = df.dropna(subset=needed)

    # Apply real-swing filter (same as 14_validation_clean)
    mask = (
        (df["bat_speed"] >= 40) & (df["bat_speed"] <= 90) &
        (df["swing_length"] >= 4) & (df["swing_length"] <= 12) &
        (df["attack_angle"].abs() <= 45)
    )
    df = df[mask].copy()
    df["intercept_z_in"] = df["plate_z"] * 12  # plate_z is in feet
    print(f"Validation sample: {len(df):,} real competitive swings")

    aa_errors = []
    arc_errors = []
    contact_errors = []
    z_mins = []
    z_maxs = []
    contact_ys = []

    for _, row in df.iterrows():
        path = reconstruct_path_2d(
            attack_angle_deg=row["attack_angle"],
            swing_length_ft=row["swing_length"],
            intercept_y_in=row["intercept_ball_minus_batter_pos_y_inches"],
            intercept_z_in=row["intercept_z_in"],
            bat_speed_mph=row["bat_speed"],
        )
        pts = path.sample(50)
        arc_num = np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()
        arc_errors.append(abs(arc_num - row["swing_length"]))
        contact_recovered = path.position_at(1.0)
        contact_errors.append(np.linalg.norm(contact_recovered - path.contact_yz))
        aa_recovered = path.bat_angle_at(1.0)
        aa_errors.append(abs(aa_recovered - row["attack_angle"]))
        z_mins.append(pts[:, 1].min())
        z_maxs.append(pts[:, 1].max())
        contact_ys.append(path.contact_yz[0])

    aa_errors = np.array(aa_errors)
    arc_errors = np.array(arc_errors)
    contact_errors = np.array(contact_errors)
    z_mins = np.array(z_mins)
    z_maxs = np.array(z_maxs)
    contact_ys = np.array(contact_ys)

    print(f"\n  Arc length error (numerical vs input):")
    print(f"    median: {np.median(arc_errors):.6f} ft   max: {arc_errors.max():.6f}")

    print(f"\n  Contact point recovery error:")
    print(f"    median: {np.median(contact_errors):.8f} ft   max: {contact_errors.max():.8f}")

    print(f"\n  Attack angle recovery error:")
    print(f"    median: {np.median(aa_errors):.4f}°")
    print(f"    max:    {aa_errors.max():.4f}°")
    print(f"    pct exactly 0 (within float precision): "
          f"{100*(aa_errors < 1e-6).mean():.2f}%")
    print(f"    pct within 0.01°: {100*(aa_errors < 0.01).mean():.2f}%")

    print(f"\n  Path height (Z) range across all swings:")
    print(f"    Median min height: {np.median(z_mins):.2f} ft")
    print(f"    Median max height: {np.median(z_maxs):.2f} ft")
    print(f"    Below ground (Z<0): {100*(z_mins<0).mean():.2f}%")
    print(f"    Above 8 ft (Z>8):   {100*(z_maxs>8).mean():.2f}%")

    print(f"\n  Contact Y (forward distance, ft):")
    print(f"    Median: {np.median(contact_ys):.2f}, range [{contact_ys.min():.2f}, {contact_ys.max():.2f}]")
    print(f"    Negative (behind batter): {100*(contact_ys<0).mean():.2f}%")

    # ==================================================================
    # Validation 3: Within-player consistency
    # ==================================================================
    print("\n" + "=" * 72)
    print("VALIDATION 3: Within-player consistency")
    print("=" * 72)

    df["batter_int"] = df["batter"].astype(int)
    test_players = {
        "Aaron Judge":  592450,
        "Steven Kwan":  680757,
        "Matt Wallner": 671213,
        "Jo Adell":     666176,
        "Nick Kurtz":   694671,
    }

    for name, mlbam in test_players.items():
        sub = df[df["batter_int"] == mlbam]
        if len(sub) < 50:
            print(f"\n  {name}: only {len(sub)} swings, skip")
            continue
        sub = sub.sample(min(300, len(sub)), random_state=42)
        paths = []
        radii = []
        for _, row in sub.iterrows():
            p = reconstruct_path_2d(
                attack_angle_deg=row["attack_angle"],
                swing_length_ft=row["swing_length"],
                intercept_y_in=row["intercept_ball_minus_batter_pos_y_inches"],
                intercept_z_in=row["intercept_z_in"],
                bat_speed_mph=row["bat_speed"],
            )
            paths.append(p.sample(18))
            radii.append(p.radius)
        paths = np.array(paths)
        mean_path = paths.mean(axis=0)
        # 2D euclidean distance per point
        spread = np.linalg.norm(paths - mean_path, axis=2)
        print(f"\n  {name} (n={len(sub)}):")
        print(f"    Mean 2D path spread:  {spread.mean():.3f} ft")
        print(f"    P95 point deviation:  {np.percentile(spread, 95):.3f} ft")
        print(f"    Max point deviation:  {spread.max():.3f} ft")
        print(f"    Radius: {np.mean(radii):.2f} ± {np.std(radii):.2f} ft")
        print(f"    Contact Y: {paths[:, -1, 0].mean():.2f} ± {paths[:, -1, 0].std():.2f} ft")
        print(f"    Contact Z: {paths[:, -1, 1].mean():.2f} ± {paths[:, -1, 1].std():.2f} ft")
