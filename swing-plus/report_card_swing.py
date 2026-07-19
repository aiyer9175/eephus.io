# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Swing+ model report card (from the independent audit). Renders via report_card_decision.render."""
from report_card_decision import render

R = dict(
    title="Swing+",
    subtitle="bat-path power / contact-quality model · independent audit",
    coverage="903 hitters · 2023H2–2026 · 1.99M pitches",
    overall="B+",
    components=[
        ("Ground truth (EV90)",  "A",  "best target r 0.66 · cleanest (self-rel 0.89)"),
        ("Descriptive accuracy", "A",  "pred EV90 R² 0.65 · calib slope 0.95–0.99"),
        ("Reliability",          "A",  "half-to-half r 0.86 · 2-yr 0.77"),
        ("Out-of-sample",        "A-", "next-half xwOBAcon r 0.54 · EV90 0.63"),
        ("Leakage",              "A",  "none — bat-tracking inputs only"),
        ("Incremental value",    "C",  "+0.006 R² over EV90+public (structural)"),
        ("Stress / tails",       "B",  "best on power; under-credits elite tail"),
        ("Champion status",      "A-", "stays champion; shrunk ≥ raw"),
    ],
    tests=[
        ("Players / pitches", "903 / 2.0M"),
        ("Best target", "EV90 (r 0.66)"),
        ("Descriptive R² (EV90)", "0.65"),
        ("Reliability (half-half)", "r 0.86"),
        ("2-year reliability", "r 0.77"),
        ("Next-half xwOBAcon", "r 0.54"),
        ("Calibration slope", "0.95–0.99"),
        ("Incremental vs EV90+pub", "+0.006 R²"),
        ("Shrunk vs raw (next)", "0.545 vs 0.537"),
        ("Challenger (GBT)", "worse (0.38)"),
    ],
    footer="Swing+ measures swing-generated power from 9 bat-tracking features. Low incremental value is structural "
           "(it reconstructs the public power metrics). A-grade at its job: isolating damage-capable swing, free of bat-to-ball.",
)

if __name__ == "__main__":
    render(R, out="web/static/swing_report_card.png")
