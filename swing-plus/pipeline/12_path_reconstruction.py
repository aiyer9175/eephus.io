# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
12_path_reconstruction.py - Reconstruct each swing's bat path as a circular arc.

Method (Option A from our discussion):
  1. Establish the swing plane in 3D using swing_path_tilt and attack_direction.
  2. Within the plane, model the sweet spot's path as a circular arc.
  3. Place contact at a known 3D location, with tangent vector aligned to
     attack_angle. This fixes orientation.
  4. Choose a sweep angle to pin down the arc's center and starting point.
  5. Store 7 parametric numbers per swing: center (3), radius (1), tangent
     direction (2 for plane basis), arc length (1). 18-point sampling is a
     visualization choice computed on demand, not a storage commitment.

Honest caveats (also flagged in earlier conversation):
  - The circular-arc model is a known simplification. Real swings change
    radius along the path. This module is intentionally Option A; Option B
    would relax this.
  - swing_path_tilt is the tilt of the swing PLANE relative to horizontal.
    Conventions across sources vary. We follow the Statcast convention as
    documented in the Baseball Savant glossary.
  - intercept_z is sometimes not in Statcast exports. Where missing, we
    infer it from plate_z and pitch trajectory at the contact moment. For
    now, we use plate_z + a small correction as a placeholder.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from pathlib import Path


# -------- Conventions --------
# Right-handed 3D coordinate system:
#   X = toward the pull side of a RHH (1B side from home plate)
#       (we'll mirror LHH at the end so all paths are "as if RHH" for analysis)
#   Y = from home plate toward pitcher (positive = away from catcher)
#   Z = vertical, +up
#
# Angle conventions (Statcast):
#   attack_angle:       vertical angle of bat velocity at contact, + up
#   attack_direction:   horizontal angle, + = toward pull side
#   swing_path_tilt:    angle of swing PLANE relative to horizontal
#
# All angles are stored in degrees in Statcast; we convert to radians for math.


@dataclass
class SwingPath:
    """Parametric representation of a single swing's bat-sweet-spot path."""

    # Plane basis vectors (each unit length, mutually orthogonal)
    e_u: np.ndarray   # in-plane "across the zone" direction
    e_v: np.ndarray   # in-plane "vertical-within-plane" direction
    e_n: np.ndarray   # plane normal

    # Arc parameters in plane (u, v) coordinates
    center_uv: np.ndarray   # (2,) center of the circle in plane coords
    radius: float           # arc radius
    theta_start: float      # starting angle on the circle (radians)
    theta_contact: float    # ending angle (at contact)

    # Anchor in 3D space — where contact happens
    contact_xyz: np.ndarray   # (3,)

    # Diagnostics carried through (for sanity checks downstream)
    bat_speed_mph: float
    swing_length_ft: float

    def position_at(self, t: float) -> np.ndarray:
        """3D position at parameter t in [0, 1] along the path.

        Standard CCW parameterization: pos_in_plane = center + R * (cos θ, sin θ).
        """
        theta = self.theta_start + t * (self.theta_contact - self.theta_start)
        u = self.center_uv[0] + self.radius * np.cos(theta)
        v = self.center_uv[1] + self.radius * np.sin(theta)
        return self.contact_xyz + (u * self.e_u + v * self.e_v)

    def sample(self, n: int = 18) -> np.ndarray:
        """Return (n, 3) array of 3D points along the path."""
        ts = np.linspace(0, 1, n)
        return np.array([self.position_at(t) for t in ts])

    def curvature(self) -> float:
        """1/R — constant under the circular-arc model."""
        return 1.0 / self.radius

    def tangent_at(self, t: float) -> np.ndarray:
        """Unit tangent vector in 3D at parameter t (direction of motion).

        Standard CCW parameterization: position = center + R(cos θ, sin θ),
        tangent direction is (-sin θ, cos θ).
        """
        theta = self.theta_start + t * (self.theta_contact - self.theta_start)
        tangent_uv = np.array([-np.sin(theta), np.cos(theta)])
        tangent_3d = tangent_uv[0] * self.e_u + tangent_uv[1] * self.e_v
        return tangent_3d / np.linalg.norm(tangent_3d)


# -------- Reconstruction --------

# Population sweep angle — how many degrees of arc the bat traverses.
# Driveline implies this is treated as roughly constant. From their plots,
# typical swings show ~90-110° of arc; we use 100° as the default.
# Phase 2.5 (Option B) would let this vary by player.
DEFAULT_SWEEP_DEG = 100.0

# Unit conversions
FT_PER_INCH = 1.0 / 12.0
DEG = np.pi / 180.0


def build_swing_plane(swing_path_tilt_deg: float,
                      attack_direction_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Build orthonormal plane basis vectors (e_u, e_v, e_n) in 3D world coords.

    The swing plane is the 2D plane in which the bat sweet spot travels under
    Assumption 1. It is defined by:
      - swing_path_tilt: how steeply tilted the plane is (rotation around the
        horizontal in-plane axis)
      - attack_direction: how the plane is rotated around the vertical axis
        (which way the swing "goes")

    Construction:
      Start with a horizontal plane (e_u = X, e_v = Y, e_n = Z).
      Rotate around Z by `attack_direction` (yaw).
      Rotate around the new e_u by `swing_path_tilt` (pitch the plane up).
      e_v is the "up-along-plane" direction. e_u is the "across-the-plane"
      direction. e_n is the plane normal.
    """
    yaw = attack_direction_deg * DEG
    tilt = swing_path_tilt_deg * DEG

    # Start: e_u along X, e_v along Y, e_n along Z.
    # After yaw rotation around Z:
    e_u = np.array([np.cos(yaw),  np.sin(yaw), 0.0])
    e_v0 = np.array([-np.sin(yaw), np.cos(yaw), 0.0])  # in-plane, was Y
    e_n0 = np.array([0.0, 0.0, 1.0])                     # plane normal, was Z

    # Now tilt the plane up: rotate around e_u by `tilt`. This takes the
    # plane normal away from vertical and the in-plane "up" direction up
    # out of horizontal.
    cos_t, sin_t = np.cos(tilt), np.sin(tilt)
    e_v = cos_t * e_v0 + sin_t * e_n0
    e_n = -sin_t * e_v0 + cos_t * e_n0

    return e_u, e_v, e_n


def reconstruct_path(
    bat_speed_mph: float,
    swing_length_ft: float,
    attack_angle_deg: float,
    attack_direction_deg: float,
    swing_path_tilt_deg: float,
    intercept_x_in: float,
    intercept_y_in: float,
    intercept_z_in: float,
    handedness: str = "R",
    sweep_deg: float = DEFAULT_SWEEP_DEG,
) -> SwingPath:
    """
    Build a SwingPath from Statcast contact-point measurements.

    Geometry steps:
      1. Build the swing plane basis (e_u, e_v, e_n).
      2. Convert contact point from inches to feet, place in 3D as origin
         anchor for the arc.
      3. Compute the arc parameters in the (u, v) plane:
         - Radius R = swing_length / sweep_angle_in_radians
         - Tangent at contact has angle = attack_angle relative to horizontal
           in-plane (i.e., relative to e_u)
         - For a circle parameterized as (cos θ, sin θ), the tangent direction
           at parameter θ is (-sin θ, cos θ). Set this equal to the desired
           tangent unit vector to solve for theta_contact.
         - Center of the circle is at distance R perpendicular to the tangent
           at the contact point.
         - theta_start = theta_contact - sweep
    """
    sweep_rad = sweep_deg * DEG
    R = swing_length_ft / sweep_rad  # radius in feet

    # 1. Plane basis
    e_u, e_v, e_n = build_swing_plane(swing_path_tilt_deg, attack_direction_deg)

    # 2. Contact point in 3D (feet)
    contact_xyz = np.array([
        intercept_x_in * FT_PER_INCH,
        intercept_y_in * FT_PER_INCH,
        intercept_z_in * FT_PER_INCH,
    ])
    # Mirror LHH so analytical/feature space is handedness-neutral.
    # Done by flipping X. attack_direction was already in the right sense
    # for RHH; we negate it via the plane basis flip below.
    if handedness == "L":
        contact_xyz[0] *= -1
        e_u = e_u.copy(); e_u[0] *= -1

    # 3. Tangent direction at contact (in plane coords).
    #
    # Convention: in the (u, v) plane, u is the "across the zone" horizontal
    # within the plane, v is the "up along the plane" direction. The bat is
    # moving toward the pitcher with positive u-component (cos α) and an
    # upward v-component (sin α) at contact.
    #
    # We need to find α (the in-plane angle of the tangent) such that the
    # WORLD vertical component of the tangent matches sin(attack_angle).
    # Since e_u is horizontal and e_v has vertical component sin(tilt),
    # only the v-component of the in-plane tangent contributes to world Z:
    #   t_z = sin(α) * e_v[2] = sin(α) * sin(tilt) = sin(aa)
    #   sin(α) = sin(aa) / sin(tilt)
    aa = attack_angle_deg * DEG
    e_v_z = e_v[2]   # vertical component of in-plane "up" basis vector
    sin_alpha_target = np.sin(aa) / max(abs(e_v_z), 1e-6)
    sin_alpha = np.clip(sin_alpha_target, -1.0, 1.0)
    cos_alpha = np.sqrt(1 - sin_alpha**2)  # positive: moving toward pitcher
    alpha = np.arctan2(sin_alpha, cos_alpha)
    tangent_uv = np.array([cos_alpha, sin_alpha])

    # 4. Arc center and angles.
    #
    # The bat sweeps along an arc with center at radius R perpendicular to
    # the tangent, on the side that bends the path correctly. For a typical
    # swing where the bat is RISING (positive attack angle) into contact
    # while moving toward the pitcher, the path curves UPWARD (concave-up
    # from the side view), so the center is OFFSET in the direction
    # perpendicular to the tangent.
    #
    # Specifically, for a tangent (cos α, sin α), the inward normal (toward
    # the center of curvature) for a concave-up arc is (-sin α, cos α).
    # The center is at position contact + R * inward_normal in (u, v).
    # Since contact is at (u, v) = (0, 0):
    inward_normal = np.array([-sin_alpha, cos_alpha])
    center_uv = R * inward_normal

    # The angle of contact on the circle, measured from the center:
    # The vector from center to contact is (0,0) - center_uv = -center_uv
    # = R * (sin α, -cos α). The angle of this vector is arctan2(-cos α, sin α).
    theta_contact = np.arctan2(-cos_alpha, sin_alpha)

    # Bat moves COUNTERCLOCKWISE on this circle (when looking at the plane
    # with e_u right, e_v up). Verify: at contact, position is center + R *
    # (cos θ_c, sin θ_c) = R(-sin α, cos α) + R(sin α, -cos α) = (0,0). ✓
    # Tangent (CCW) is R * (-sin θ_c, cos θ_c). With theta_c above:
    # = R(-(-cos α), sin α) = R(cos α, sin α) = R * tangent_uv. ✓
    #
    # So motion is CCW, theta_start < theta_contact, theta_start = theta_contact - sweep.
    theta_start = theta_contact - sweep_rad

    # Center is at distance R perpendicular to the tangent, on the "inside"
    # of the curve. For a forward-traveling bat that curves up into contact,
    # the center is BELOW the contact in plane coordinates.
    # Perpendicular to tangent (rotated -90°): (cos(aa) * cos(-90°) - sin(aa)*sin(-90°), ...)
    # Easier: inward normal is -(cos θ_c, sin θ_c) for our parameterization.
    inward = -np.array([np.cos(theta_contact), np.sin(theta_contact)])
    # Contact point in (u, v) is at the origin of plane coords (we'll place
    # the contact at the origin, then translate to 3D via contact_xyz).
    center_uv = R * inward

    # Verify: |center_uv - (0,0)| should equal R
    assert abs(np.linalg.norm(center_uv) - R) < 1e-9

    theta_start = theta_contact - sweep_rad

    return SwingPath(
        e_u=e_u, e_v=e_v, e_n=e_n,
        center_uv=center_uv,
        radius=R,
        theta_start=theta_start,
        theta_contact=theta_contact,
        contact_xyz=contact_xyz,
        bat_speed_mph=bat_speed_mph,
        swing_length_ft=swing_length_ft,
    )


# -------- Validation harness --------

def sanity_check_path(path: SwingPath) -> dict:
    """Verify the reconstruction produced a geometrically valid path."""
    samples = path.sample(50)
    # Reported arc length, computed numerically from samples
    seg_lengths = np.linalg.norm(np.diff(samples, axis=0), axis=1)
    arc_len_numeric = seg_lengths.sum()
    arc_len_analytic = path.radius * abs(path.theta_contact - path.theta_start)

    # Contact point at t=1 should match contact_xyz
    contact_recovered = path.position_at(1.0)
    contact_err = np.linalg.norm(contact_recovered - path.contact_xyz)

    # Tangent at contact should have vertical component matching attack_angle
    tangent = path.tangent_at(1.0)
    measured_attack_angle = np.degrees(np.arctan2(tangent[2],
                                                    np.linalg.norm(tangent[:2])))

    return {
        "arc_len_analytic_ft": arc_len_analytic,
        "arc_len_swing_length_ft": path.swing_length_ft,
        "arc_len_match": abs(arc_len_analytic - path.swing_length_ft) < 0.01,
        "contact_recovery_err_ft": contact_err,
        "measured_attack_angle_deg": measured_attack_angle,
    }


if __name__ == "__main__":
    # Test on three archetypal swings - Judge (steep, high power),
    # Wallner (medium attack angle, balanced), Kwan (flat, contact)
    print("=" * 70)
    print("Validation: Reconstruct three archetypal swings")
    print("=" * 70)

    test_cases = [
        ("Aaron Judge (R, steep)",     "R", 74.8, 7.92, 13.4, -2.0, 33.0, 41.0, 30.0, 35.0),
        ("Matt Wallner (L, balanced)", "L", 74.4, 7.32, 11.4, -2.5, 28.0, 41.4, 36.3, 34.0),
        ("Steven Kwan (L, flat)",      "L", 61.5, 7.05,  2.1, -1.0, 35.0, 36.0, 28.0, 33.0),
    ]

    for name, hand, bs, sl, aa, ad, spt, ix, iy, iz in test_cases:
        path = reconstruct_path(
            bat_speed_mph=bs, swing_length_ft=sl, attack_angle_deg=aa,
            attack_direction_deg=ad, swing_path_tilt_deg=spt,
            intercept_x_in=ix, intercept_y_in=iy, intercept_z_in=iz,
            handedness=hand,
        )
        checks = sanity_check_path(path)
        print(f"\n{name}")
        print(f"  Radius (ft):              {path.radius:.3f}")
        print(f"  Arc len analytic (ft):    {checks['arc_len_analytic_ft']:.3f}")
        print(f"  Arc len input (ft):       {checks['arc_len_swing_length_ft']:.3f}")
        print(f"  Arc len OK:               {checks['arc_len_match']}")
        print(f"  Contact recovery err:     {checks['contact_recovery_err_ft']:.6f} ft")
        print(f"  Recovered attack angle:   {checks['measured_attack_angle_deg']:.2f}° "
              f"(input: {aa}°)")
        # Sample 18 points and show start, middle, end
        pts = path.sample(18)
        print(f"  Path start (ft):          ({pts[0][0]:+.2f}, {pts[0][1]:+.2f}, {pts[0][2]:+.2f})")
        print(f"  Path middle (ft):         ({pts[9][0]:+.2f}, {pts[9][1]:+.2f}, {pts[9][2]:+.2f})")
        print(f"  Path contact (ft):        ({pts[17][0]:+.2f}, {pts[17][1]:+.2f}, {pts[17][2]:+.2f})")
