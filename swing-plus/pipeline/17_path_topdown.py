# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
17_path_topdown.py - Top-down view of the swing path.

Geometry:
  - Work in the (X, Y) plane: X = lateral (+ pull), Y = depth (+ pitcher).
  - Contact point: (intercept_x, intercept_y) in feet, with LHH mirrored.
  - Tangent at contact: derived from attack_direction.
    attack_direction = 0  → tangent = (0, 1)   (straight toward pitcher)
    attack_direction > 0  → tangent rotates toward +X (pull side)
    attack_direction < 0  → tangent rotates toward -X (oppo side)
  - Curvature: concave toward pull side (bat wraps around body).

This is the SAME circular-arc model as the side view, just in a different
2D plane. The two reconstructions are independent — they share inputs
(swing_length, intercept_y, handedness) but don't share their geometric
construction. We will not try to make them produce a consistent 3D path.
Instead, we treat them as two independent views, each useful for different
features.

What this gives us that the side view doesn't:
  - Horizontal Attack Angle (HAA) at three buckets (Downswing, Contact Zone,
    Follow-Through) - matches Driveline's framework
  - Lateral path coverage (how much does the swing wrap around?)

Honest caveats:
  - The "horizontal radius" uses the same arc-length-over-sweep formula
    as the side view. This is not physically correct (3D path length ≠
    side-view length ≠ top-down length), but it's consistent and the
    features we extract (HAA at three points) are robust to the choice.
  - We assume bat curvature is toward pull side. This holds for the
    last 50% of the swing (around contact) where the wrist roll dominates.
    The "Downswing" portion may show the opposite curvature in reality.
    Our reconstruction will not capture that nuance.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass


DEFAULT_SWEEP_DEG = 100.0
DEG = np.pi / 180.0
FT_PER_INCH = 1.0 / 12.0


@dataclass
class SwingPath2D_TopDown:
    """Top-down (X, Y) parametric path."""
    center_xy: np.ndarray
    radius: float
    theta_start: float
    theta_contact: float
    contact_xy: np.ndarray

    # Pass-through
    attack_direction_deg: float
    swing_length_ft: float
    handedness: str

    def position_at(self, t: float) -> np.ndarray:
        # theta_start > theta_contact for CW motion. As t increases from
        # 0 to 1, theta decreases from theta_start to theta_contact.
        theta = self.theta_start + t * (self.theta_contact - self.theta_start)
        return self.center_xy + self.radius * np.array([np.cos(theta), np.sin(theta)])

    def sample(self, n: int = 18) -> np.ndarray:
        return np.array([self.position_at(t) for t in np.linspace(0, 1, n)])

    def tangent_at(self, t: float) -> np.ndarray:
        """Unit tangent vector at parameter t. CW motion means tangent is
        the negative of the standard CCW derivative."""
        theta = self.theta_start + t * (self.theta_contact - self.theta_start)
        # CCW position derivative: (-sin θ, cos θ). For CW motion (θ
        # decreasing in t), motion direction is the NEGATIVE: (sin θ, -cos θ).
        tangent = np.array([np.sin(theta), -np.cos(theta)])
        return tangent / np.linalg.norm(tangent)

    def haa_at(self, t: float) -> float:
        """Horizontal Attack Angle in degrees: 0 = toward pitcher, + = toward pull."""
        tangent = self.tangent_at(t)
        return np.degrees(np.arctan2(tangent[0], tangent[1]))


def reconstruct_topdown(
    attack_direction_deg: float,
    swing_length_ft: float,
    intercept_x_in: float,
    intercept_y_in: float,
    handedness: str = "R",
    sweep_deg: float = DEFAULT_SWEEP_DEG,
) -> SwingPath2D_TopDown:
    """
    Reconstruct top-down view path.

    Convention: after mirroring LHH, X is always "pull" (positive) and the
    bat always curves toward +X as it approaches contact. We mirror LHH by
    flipping the sign of both intercept_x and attack_direction (which gives
    us a unified "as if RHH" representation for analysis).
    """
    # Mirror LHH so all paths analyzed as RHH
    if handedness == "L":
        intercept_x_in = -intercept_x_in
        attack_direction_deg = -attack_direction_deg

    sweep_rad = sweep_deg * DEG
    R = swing_length_ft / sweep_rad  # same as side-view radius

    # Contact location in (X, Y) feet
    contact_xy = np.array([
        intercept_x_in * FT_PER_INCH,
        intercept_y_in * FT_PER_INCH,
    ])

    # Geometric reasoning for the top-down view:
    #
    # A RHH (post-mirroring, all batters analyzed as RHH) loads the bat
    # over the back shoulder, which in FIELD COORDINATES is on the
    # PULL side (+X for RHH). As the swing executes, the bat sweeps
    # from "pull-and-back" around toward "forward-and-centered" at
    # contact. So the CENTER of the circular arc is on the PULL side
    # (+X), and the bat orbits this center as it travels from start to
    # contact.
    #
    # Required at contact (β=0): tangent direction = +Y (toward pitcher).
    # If center is at +R on X-axis (pull side), and contact is at (0, 0),
    # then position = center + R(cos θ, sin θ) means at contact:
    # (0, 0) = (R, 0) + R(cos θ_c, sin θ_c), so (cos θ_c, sin θ_c) = (-1, 0),
    # which gives θ_c = π.
    #
    # For tangent to be +Y at θ_c = π, motion must be CLOCKWISE (θ
    # decreasing), because:
    #   CW tangent = -(d position / d θ) = (sin θ, -cos θ)
    #   At θ_c = π: CW tangent = (0, 1) ✓
    #
    # General case (β ≠ 0): tangent at contact = (sin β, cos β).
    # Center direction from contact = rotate tangent 90° CW = (cos β, -sin β).
    # So center = contact + R * (cos β, -sin β).
    beta = attack_direction_deg * DEG
    sin_b, cos_b = np.sin(beta), np.cos(beta)
    tangent_at_contact = np.array([sin_b, cos_b])

    inward = np.array([cos_b, -sin_b])  # rotate tangent 90° CW
    center_xy = contact_xy + R * inward

    # Contact's angle on the circle (from center):
    # vec from center to contact = -R * inward = R(-cos_b, sin_b)
    # θ_c = arctan2(sin_b, -cos_b) = π - β
    theta_contact = np.pi - beta

    # CW motion: θ decreases from start to contact.
    # So theta_start = theta_contact + sweep.
    theta_start = theta_contact + sweep_rad

    return SwingPath2D_TopDown(
        center_xy=center_xy,
        radius=R,
        theta_start=theta_start,
        theta_contact=theta_contact,
        contact_xy=contact_xy,
        attack_direction_deg=attack_direction_deg,
        swing_length_ft=swing_length_ft,
        handedness=handedness,
    )


# ==================================================================
# Validation 1: Single-swing geometric correctness
# ==================================================================

if __name__ == "__main__":
    print("=" * 72)
    print("VALIDATION 1: Single-swing geometric correctness (top-down)")
    print("=" * 72)

    test_cases = [
        # (name, attack_direction, swing_length, intercept_x_in, intercept_y_in, hand)
        ("Straight to pitcher (R)",  0.0, 7.5, 0.0,  30.0, "R"),
        ("Pull-side RHH",            +20.0, 7.5, -2.0, 28.0, "R"),
        ("Oppo-side RHH",            -15.0, 7.5, +5.0, 26.0, "R"),
        ("Straight to pitcher (L)",  0.0, 7.5, 0.0,  30.0, "L"),
        ("Pull-side LHH",            -20.0, 7.5, +2.0, 28.0, "L"),
    ]

    print(f"\n{'Name':<30}{'AD in':>10}{'HAA at contact':>16}{'AD err':>10}")
    print("-" * 70)
    for name, ad, sl, ix, iy, hand in test_cases:
        # NOTE: input attack_direction in the LHH cases needs to flip sign
        # internally; after mirroring, we should recover the original
        # (un-flipped) magnitude of attack_direction. But the convention
        # we want is "post-mirroring everything is RHH". So the recovered
        # angle should equal:
        #   - For RHH inputs: attack_direction as given
        #   - For LHH inputs: -attack_direction (because we flipped it)
        path = reconstruct_topdown(ad, sl, ix, iy, hand)
        haa = path.haa_at(1.0)
        expected = ad if hand == "R" else -ad
        err = abs(haa - expected)
        print(f"{name:<30}{ad:>10.2f}{haa:>16.3f}{err:>10.3f}")

    # Sample a path and look at coordinates
    p = reconstruct_topdown(0.0, 7.5, 0.0, 30.0, "R")
    pts = p.sample(7)
    print(f"\nStraight-to-pitcher RHH path samples (X, Y) in feet:")
    for i, pt in enumerate(pts):
        print(f"  t={i/6:.2f}:  X = {pt[0]:+.3f}, Y = {pt[1]:+.3f}")
    print(f"  Bat should start back-and-oppo, end forward-and-on-line.")
    print(f"  At β=0, bat should be at X=0 at contact, more positive X earlier.")
    print(f"  (Positive X = pull side = wraps around body)")

    # ==================================================================
    # Validation 2: Real data, full sweep
    # ==================================================================
    print("\n" + "=" * 72)
    print("VALIDATION 2: Geometric correctness on real Statcast 2025 H1")
    print("=" * 72)

    df = pd.read_parquet("data/raw/statcast_2025_H1.parquet")
    df = df[df["bat_speed"].notna() & df["swing_length"].notna()].copy()
    needed = ["bat_speed", "swing_length", "attack_angle", "attack_direction",
              "intercept_ball_minus_batter_pos_x_inches",
              "intercept_ball_minus_batter_pos_y_inches", "plate_z", "stand"]
    df = df.dropna(subset=needed)
    mask = (
        (df["bat_speed"] >= 40) & (df["bat_speed"] <= 90) &
        (df["swing_length"] >= 4) & (df["swing_length"] <= 12) &
        (df["attack_angle"].abs() <= 45) &
        (df["attack_direction"].abs() <= 60)
    )
    df = df[mask].copy()
    print(f"Validation sample: {len(df):,} swings")

    haa_errors = []
    arc_errors = []
    contact_errors = []
    contact_xs_post_mirror = []
    haa_at_contact = []
    haa_at_downswing = []

    for _, row in df.iterrows():
        path = reconstruct_topdown(
            attack_direction_deg=row["attack_direction"],
            swing_length_ft=row["swing_length"],
            intercept_x_in=row["intercept_ball_minus_batter_pos_x_inches"],
            intercept_y_in=row["intercept_ball_minus_batter_pos_y_inches"],
            handedness=row["stand"],
        )
        haa_c = path.haa_at(1.0)
        haa_at_contact.append(haa_c)
        haa_at_downswing.append(path.haa_at(0.17))  # ~1/6 in

        expected = row["attack_direction"] if row["stand"] == "R" else -row["attack_direction"]
        haa_errors.append(abs(haa_c - expected))

        pts = path.sample(50)
        arc_num = np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()
        arc_errors.append(abs(arc_num - row["swing_length"]))
        contact_errors.append(np.linalg.norm(path.position_at(1.0) - path.contact_xy))
        contact_xs_post_mirror.append(path.contact_xy[0])

    haa_errors = np.array(haa_errors)
    arc_errors = np.array(arc_errors)
    contact_errors = np.array(contact_errors)
    contact_xs_post_mirror = np.array(contact_xs_post_mirror)
    haa_at_contact = np.array(haa_at_contact)
    haa_at_downswing = np.array(haa_at_downswing)

    print(f"\n  HAA recovery error (recovered vs expected):")
    print(f"    median: {np.median(haa_errors):.6f}°  max: {haa_errors.max():.6f}°")
    print(f"    pct exact (within 1e-6°): {100*(haa_errors < 1e-6).mean():.2f}%")

    print(f"\n  Arc length error:")
    print(f"    median: {np.median(arc_errors):.6f} ft  max: {arc_errors.max():.6f}")

    print(f"\n  Contact recovery:")
    print(f"    median: {np.median(contact_errors):.8f} ft  max: {contact_errors.max():.8f}")

    print(f"\n  Post-mirror contact X distribution (all paths analyzed as RHH):")
    print(f"    median: {np.median(contact_xs_post_mirror):+.2f} in ft")
    print(f"    range:  [{contact_xs_post_mirror.min():+.2f}, "
          f"{contact_xs_post_mirror.max():+.2f}]")
    print(f"    (Should be roughly centered around 0 if the L mirror works")
    print(f"     correctly. Slight + skew is expected because RHH pull = +X.)")

    print(f"\n  HAA evolution along the path (sanity: does it CHANGE between")
    print(f"  Downswing and Contact? If they're identical, the curvature isn't")
    print(f"  doing anything.):")
    haa_change = haa_at_downswing - haa_at_contact
    print(f"    HAA at Downswing - HAA at Contact:")
    print(f"      median change: {np.median(haa_change):+.2f}°")
    print(f"      p10, p90:      [{np.percentile(haa_change, 10):+.2f}, "
          f"{np.percentile(haa_change, 90):+.2f}]")
    print(f"    (Expected: large positive — the bat is much further toward pull")
    print(f"     during the downswing than at contact. Driveline reports HAA")
    print(f"     swings of ~50° from Downswing to Contact Zone for typical hitters.)")


    # ==================================================================
    # Validation 3: Sanity check on contact direction
    # ==================================================================
    print("\n" + "=" * 72)
    print("VALIDATION 3: Direction-of-motion sanity check")
    print("=" * 72)
    print("At contact, the bat should be moving TOWARD the pitcher (+Y).")
    print("If our reconstruction has wrong rotation direction, Y component < 0.")

    sample = df.sample(1000, random_state=0)
    pos_y_count = 0
    for _, row in sample.iterrows():
        path = reconstruct_topdown(
            attack_direction_deg=row["attack_direction"],
            swing_length_ft=row["swing_length"],
            intercept_x_in=row["intercept_ball_minus_batter_pos_x_inches"],
            intercept_y_in=row["intercept_ball_minus_batter_pos_y_inches"],
            handedness=row["stand"],
        )
        tangent_at_contact = path.tangent_at(1.0)
        if tangent_at_contact[1] > 0:
            pos_y_count += 1
    print(f"  Tangent has +Y component at contact: "
          f"{pos_y_count}/1000 = {100*pos_y_count/1000:.1f}%")
    print(f"  (Should be 100% — the bat moves toward the pitcher at contact.)")
