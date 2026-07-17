/*
 Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
 Unauthorized copying of this file, via any medium is strictly prohibited
 Proprietary and confidential
 Written by Will Cahoon (@willcolqhn), 2026
*/

// swing3d.js — three.js 3D swing-PLANE visualization (no batter, no plate).
// The whole bat lies IN a single tilted plane and rotates within it (on-plane),
// so the barrel traces a circle that lives entirely in the swing plane. The plane
// is defined by: swing tilt (steepness), attack direction (azimuth/aim), and the
// attack angle is the slope of the bat's travel as it passes through contact.
// A translucent disc shows the plane; the bat sweeps; the measured contact zone
// glows. Current vs adjusted overlaid. Rotatable camera.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

let _state = null;

export function disposeSwing3D() {
  if (!_state) return;
  cancelAnimationFrame(_state.raf);
  window.removeEventListener("resize", _state.onResize);
  _state.controls.dispose();
  _state.renderer.dispose();
  const el = _state.renderer.domElement;
  if (el.parentNode) el.parentNode.removeChild(el);
  if (_state.overlay && _state.overlay.parentNode) _state.overlay.parentNode.removeChild(_state.overlay);
  if (_state.replayBtn && _state.replayBtn.parentNode) _state.replayBtn.parentNode.removeChild(_state.replayBtn);
  if (_state.panel && _state.panel.parentNode) _state.panel.parentNode.removeChild(_state.panel);
  _state = null;
}

// World axes: x = pull(+)/oppo(-), y = up, z = toward pitcher(+).
// Build an orthonormal basis for the swing plane:
//   inPlaneX  = the "long" axis the bat travels along (tangent at contact = attack angle)
//   inPlaneY  = the other in-plane axis (perpendicular, within the plane)
//   normal    = plane normal
function planeBasis(p) {
  const aa = THREE.MathUtils.degToRad(p.attack_angle);  // travel slope at contact
  const dir = THREE.MathUtils.degToRad(p.attack_dir);   // azimuth (pull +)
  const tilt = THREE.MathUtils.degToRad(p.tilt);        // plane steepness from horizontal

  // tangent at contact: rises by attack angle, aimed in azimuth. attack_dir is
  // pull-POSITIVE (Savant convention); pull aims toward -x so the plane azimuth
  // agrees with the attack-direction reveal ray (which also puts pull at -x).
  const tangent = new THREE.Vector3(
    -Math.sin(dir) * Math.cos(aa),
    Math.sin(aa),
    Math.cos(dir) * Math.cos(aa)
  ).normalize();

  // Swing tilt = angle of the swing PLANE from horizontal. So the in-plane axis
  // perpendicular to the tangent rises out of the ground by `tilt`:
  //   tilt = 0   -> plane flat (horizontal), inPlaneY horizontal
  //   tilt = 90  -> plane vertical, inPlaneY straight up
  // horizontal axis perpendicular to the tangent (in the ground plane):
  const horiz = new THREE.Vector3(tangent.z, 0, -tangent.x).normalize();
  // inPlaneY = horiz tipped up out of the ground by `tilt` (rotate about tangent):
  const inPlaneY = horiz.clone().applyAxisAngle(tangent, tilt).normalize();
  const normal = new THREE.Vector3().crossVectors(tangent, inPlaneY).normalize();
  return { tangent, inPlaneY, normal, aa, dir, tilt };
}

// Swing circle of radius R lying in the plane. The center is fixed; `dir(phi)`
// is the unit direction from center to a point on the circle. At phi=0 the
// direction points to contact (the low point), tangent = travel at contact.
function swingCircle(b, R, contact) {
  const radial = b.inPlaneY.clone().multiplyScalar(-1);   // center -> contact
  const center = contact.clone().addScaledVector(radial, -R);
  const dir = phi => radial.clone().multiplyScalar(Math.cos(phi))
    .addScaledVector(b.tangent, Math.sin(phi)).normalize();
  return { center, dir };
}
// barrel point on the circle (radius R from the shared center).
function barrelAt(b, phi, R, contact) {
  const c = swingCircle(b, R, contact);
  return c.center.clone().addScaledVector(c.dir(phi), R);
}

export function renderSwing3D(container, cur, adj) {
  disposeSwing3D();
  const W = container.clientWidth || 760, H = 440;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0f1830);

  // Handedness: the model stores swing features pull-neutral, so a lefty and righty
  // with the same numbers look identical. We mirror the whole scene in x for LHB so
  // the lefty stands in the correct box and the swing rotates the correct way.
  const SX = (cur && cur.stand === "L") ? -1 : 1;

  const camera = new THREE.PerspectiveCamera(40, W / H, 0.1, 100);
  // tighter 3/4 view from the catcher's side, framing the disc + plate (mirrored for LHB)
  camera.position.set(-6.4 * SX, 3.5, 5.0);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(W, H); renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.domElement.style.display = "block";
  container.style.position = "relative";
  container.appendChild(renderer.domElement);
  // overlay layer for HTML callout labels
  const overlay = document.createElement("div");
  overlay.style.cssText = "position:absolute;inset:0;pointer-events:none;";
  container.appendChild(overlay);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 2.0, 0); controls.enablePan = false;
  controls.minDistance = 5; controls.maxDistance = 130; controls.update();
  // the guided sequence drives the camera ("auto"); any user drag hands control back
  let camMode = "auto";
  controls.addEventListener("start", () => { camMode = "free"; });

  scene.add(new THREE.HemisphereLight(0xcfe0ff, 0x22304a, 1.2));
  const dl = new THREE.DirectionalLight(0xffffff, 0.6); dl.position.set(-4, 9, 6); scene.add(dl);

  // everything that should mirror for handedness lives under `world`
  const world = new THREE.Group(); world.scale.x = SX; scene.add(world);

  const R = 2.7;                              // swing radius: knob(center) -> barrel(arc)
  const PHI_A = -2.0, PHI_B = 1.5, WINr = 0.45;
  const IN = 1 / 12;                          // inches -> world units (plate = 17in = 1.42u)
  // CONTACT POINT from the player's tracked intercept: depth (y, out in front) and
  // lateral (x). Height isn't tracked, so it's a fixed belt-height nominal.
  const FRONT = 0.71;                         // plate front edge (z toward pitcher)
  const depthIn = (cur && cur.depth != null) ? cur.depth : 30;   // inches in front of body
  const sideIn  = (cur && cur.contact_side != null) ? cur.contact_side : 37; // lateral reach (in)
  const contactZ = FRONT + (depthIn - 20) * IN;                  // out in front of the plate
  const contact = new THREE.Vector3(0, 2.6, contactZ);          // lateral ~ over the plate
  controls.target.set(0, 2.0, contactZ * 0.45);

  // --- home plate: vertices in WORLD coords on the ground (y=0). z+ = toward
  // pitcher, z- = toward catcher. Flat 17" edge faces the pitcher; the point
  // faces the catcher. (Built directly to avoid rotation sign confusion.) ---
  const pv = [
    [-0.71, 0,  0.71],   // front-left (toward pitcher)
    [ 0.71, 0,  0.71],   // front-right
    [ 0.71, 0, -0.20],   // right side
    [ 0.00, 0, -0.85],   // back POINT (toward catcher)
    [-0.71, 0, -0.20],   // left side
  ];
  const pg = new THREE.BufferGeometry();
  const tri = [0,1,2, 0,2,3, 0,3,4];   // fan from front-left
  pg.setAttribute("position", new THREE.Float32BufferAttribute(
    tri.flatMap(i => pv[i]), 3));
  pg.computeVertexNormals();
  const plate = new THREE.Mesh(pg, new THREE.MeshBasicMaterial({
    color: 0xeef2f7, transparent: true, opacity: 1, depthWrite: false, side: THREE.DoubleSide }));
  plate.position.y = 0.02; plate.renderOrder = 30; world.add(plate);   // above the dirt skin
  const loop = pv.map(p => new THREE.Vector3(p[0], 0.03, p[2]));
  loop.push(loop[0].clone());
  const ploop = new THREE.Line(new THREE.BufferGeometry().setFromPoints(loop),
    new THREE.LineBasicMaterial({ color: 0x9fb3cc, transparent: true, depthWrite: false }));
  ploop.renderOrder = 31; world.add(ploop);

  // ===== field (true scale, 1u = 1ft). EVERY flat ground layer is transparent with
  // depthWrite:false + an ascending renderOrder, so coplanar surfaces paint strictly
  // back-to-front and never z-fight. (No fragile y-stacking.) Layout follows the photo:
  // grass, a continuous dirt infield skin, home dirt circle, boxes, plate lines, bases.
  (function buildField() {
    let RO = 1;
    function flat(geo, color, op, dbl) {              // flat (ground-plane) mesh
      const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, transparent: true,
        opacity: op, depthWrite: false, side: dbl ? THREE.DoubleSide : THREE.FrontSide }));
      m.rotation.x = -Math.PI / 2; m.renderOrder = RO++; world.add(m); return m;
    }
    function strip(ax, az, bx, bz, w, color, op) {   // dirt path a->b, width w
      const dx = bx - ax, dz = bz - az, L = Math.hypot(dx, dz) || 1;
      const px = -dz / L * (w / 2), pz = dx / L * (w / 2);
      const P = [[ax+px,0,az+pz],[ax-px,0,az-pz],[bx-px,0,bz-pz],[bx+px,0,bz+pz]];
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(
        [...P[0],...P[1],...P[2], ...P[0],...P[2],...P[3]], 3));
      const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color, transparent: true,
        opacity: op, depthWrite: false, side: THREE.DoubleSide }));
      m.renderOrder = RO++; world.add(m); return m;
    }
    function gline(pts, color, op, y) {              // chalk line on the ground (or zone)
      const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(
        pts.map(p => new THREE.Vector3(p[0], y, p[1]))),
        new THREE.LineBasicMaterial({ color, transparent: true, opacity: op, depthWrite: false }));
      l.renderOrder = RO++; world.add(l); return l;
    }
    const D90 = 90 / Math.SQRT2, B2 = 127.28, FL = 150 / Math.SQRT2;
    const DIRT = 0x6e4d34, GRASS = 0x14401f, CHALK = 0xeef3fb;

    flat(new THREE.PlaneGeometry(520, 520), GRASS, 0.75).position.z = 70;   // outfield grass
    // continuous dirt infield skin: home circle + the diamond basepaths (one look)
    strip(0, 0, D90, D90, 7, DIRT, 0.92);            // home -> 1B
    strip(0, 0, -D90, D90, 7, DIRT, 0.92);           // home -> 3B
    strip(D90, D90, 0, B2, 7, DIRT, 0.92);           // 1B -> 2B
    strip(-D90, D90, 0, B2, 7, DIRT, 0.92);          // 3B -> 2B
    flat(new THREE.CircleGeometry(13, 64), DIRT, 0.92);            // home dirt circle
    flat(new THREE.CircleGeometry(9, 48), DIRT, 0.92).position.z = 60.5;   // mound
    for (const x of [D90, -D90, 0])                  // base cutouts (1B/3B/2B)
      flat(new THREE.CircleGeometry(4, 32), DIRT, 0.92).position.set(x, 0, x === 0 ? B2 : D90);
    // foul lines + batter's boxes + catcher's box (white chalk)
    gline([[0, -0.85], [FL, FL]], CHALK, 0.65, 0.02);
    gline([[0, -0.85], [-FL, FL]], CHALK, 0.65, 0.02);
    const bw = 2, bl = 3, cx = 0.71 + 0.5 + bw;       // batter's box: 4ft x 6ft, 6in off plate
    for (const s of [-1, 1]) {
      const active = (s === -1);                      // hitter stands in the -x box (LHB mirrors)
      gline([[s*cx-bw, -bl-0.1], [s*cx+bw, -bl-0.1], [s*cx+bw, bl-0.1],
             [s*cx-bw, bl-0.1], [s*cx-bw, -bl-0.1]], active ? 0xffe9bf : CHALK, active ? 1 : 0.55, 0.03);
      if (active)
        flat(new THREE.PlaneGeometry(2*bw, 2*bl), 0xe8d2a0, 0.16).position.set(s*cx, 0, -0.1);
    }
    gline([[-1.79, -0.85], [1.79, -0.85], [1.79, -8.85], [-1.79, -8.85], [-1.79, -0.85]],
          CHALK, 0.45, 0.02);                         // catcher's box behind home
    // bases + rubber (white)
    for (const b of [[D90, D90], [-D90, D90], [0, B2]]) {
      const bag = flat(new THREE.PlaneGeometry(1.5, 1.5), CHALK, 1);
      bag.rotation.z = Math.PI / 4; bag.position.set(b[0], 0, b[1]);
    }
    flat(new THREE.PlaneGeometry(2, 0.5), CHALK, 1).position.z = 60.5;     // pitching rubber
    // strike zone (vertical): knees(1.5)..letters(3.5), at the plate front
    const zx = 0.71, z0 = 1.5, z1 = 3.5, zz = FRONT, zc = 0xbcd0ea;
    const zline = pts => { const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: zc, transparent: true, opacity: 0.45, depthWrite: false }));
      l.renderOrder = RO++; world.add(l); };
    zline([[-zx,z0,zz],[zx,z0,zz],[zx,z1,zz],[-zx,z1,zz],[-zx,z0,zz]].map(p=>new THREE.Vector3(...p)));
    for (let i = 1; i < 3; i++) { const xx = -zx + 2*zx*i/3, yy = z0 + (z1-z0)*i/3;
      zline([new THREE.Vector3(xx,z0,zz), new THREE.Vector3(xx,z1,zz)]);
      zline([new THREE.Vector3(-zx,yy,zz), new THREE.Vector3(zx,yy,zz)]); }
  })();

  // --- pitch path the ball travels IN along (from the mound side to contact) ---
  // The ball meets the barrel at `contactBall`, a hair off the barrel tip so the
  // two models touch but never merge. tang = bat travel at contact (the attack
  // angle in 3D) = the direction the ball leaves, back toward where it came from.
  const curB = planeBasis(cur);
  const tang = curB.tangent.clone();
  const contactBall = contact.clone().addScaledVector(tang, 0.26);
  // release point ~54 ft out (≈6.5 ft of extension in front of the 60'6" rubber)
  const pStart = new THREE.Vector3(0.7, 5.8, 54);
  function pitchPos(u) {  // horizontal at constant speed; vertical falls under gravity
    // y drops MONOTONICALLY (small early, faster late) — a real pitch never rises.
    const drop = 0.18 * u + 0.82 * u * u;            // gravity-weighted ease, 0->1
    return new THREE.Vector3(
      pStart.x + (contactBall.x - pStart.x) * u,
      pStart.y + (contactBall.y - pStart.y) * drop,
      pStart.z + (contactBall.z - pStart.z) * u);
  }
  const pitchPts = []; for (let i = 0; i <= 40; i++) pitchPts.push(pitchPos(i / 40));
  const pitchLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pitchPts),
    new THREE.LineDashedMaterial({ color: 0xe0a93c, dashSize: 0.22, gapSize: 0.16,
      transparent: true, opacity: 0.6 }));
  pitchLine.computeLineDistances(); pitchLine.visible = false; world.add(pitchLine);

  function buildSwing(p, planeColor, pathColor, zoneColor, showPlane, planeOpacity) {
    const b = planeBasis(p);
    const grp = new THREE.Group();
    // 1) translucent swing-plane disc
    if (showPlane) {
      const disc = new THREE.Mesh(
        new THREE.CircleGeometry(R * 1.15, 48),
        new THREE.MeshBasicMaterial({ color: planeColor, transparent: true,
          opacity: planeOpacity, side: THREE.DoubleSide, depthWrite: false }));
      // orient disc to the plane: its local +z should be the plane normal
      const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), b.normal);
      disc.quaternion.copy(q);
      const center = contact.clone().addScaledVector(b.inPlaneY.clone().multiplyScalar(-1), -R);
      disc.position.copy(center);
      grp.add(disc);
    }
    // 2) full barrel path (faint ring) + measured-zone arc (bright)
    const ringPts = [], zonePts = [];
    for (let i = 0; i <= 140; i++) { const phi = -Math.PI + 2 * Math.PI * i / 140;
      ringPts.push(barrelAt(b, phi, R, contact)); }
    grp.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(ringPts),
      new THREE.LineBasicMaterial({ color: pathColor, transparent: true, opacity: 0.35 })));
    for (let i = 0; i <= 50; i++) { const phi = -WINr + 2 * WINr * i / 50;
      zonePts.push(barrelAt(b, phi, R, contact)); }
    grp.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(zonePts),
      new THREE.LineBasicMaterial({ color: zoneColor })));
    world.add(grp);
    return { b, grp };
  }

  const adjS = buildSwing(adj, 0x2ecc71, 0x2ecc71, 0x7fe0a8, true, 0.10);
  const curS = buildSwing(cur, 0x4f9eff, 0xa9c6ea, 0xffffff, true, 0.16);

  // --- launch path the ball flies OUT along after contact (the attack angle!) ---
  // direction = the bat's travel/tangent at contact = the attack angle in 3D.
  const launchDir = tang.clone();                     // leaves at the attack angle,
  function launchPos(u) {  // ...straight along the attack angle (no droop), HIGH VELOCITY
    const D = 150;        // explosive jump off the bat — carries to the outfield (real ft)
    const d = D * (0.5 * u + 0.5 * u * u);
    return contactBall.clone().addScaledVector(launchDir, d);
  }
  const launchPts = []; for (let i = 0; i <= 24; i++) launchPts.push(launchPos(i / 24));
  const launchLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(launchPts),
    new THREE.LineDashedMaterial({ color: 0xffffff, dashSize: 0.25, gapSize: 0.18,
      transparent: true, opacity: 0.55 }));
  launchLine.computeLineDistances(); launchLine.visible = false; world.add(launchLine);

  // --- the live bat: a real bat that is a RADIUS of the swing circle ---
  // knob sits at the disc CENTER (the rotation axis); the barrel rides on the
  // arc at radius R. Built pointing +Y (knob at origin, barrel at +R); we place
  // it by setting position=center and rotating +Y onto the current radial dir.
  const DS = THREE.DoubleSide;   // mirrored (world.scale.x<0) needs DoubleSide to light right
  // smooth one-piece bat from two lathes (solids of revolution) — a real bat
  // silhouette: flared knob -> thin handle (dark) -> tapered flared barrel (light)
  // -> domed end. Knob at the center (y=0), barrel end on the arc (y=R).
  const bat = new THREE.Group();
  const lathe = (pts, color, rough) => {
    const g = new THREE.LatheGeometry(pts.map(p => new THREE.Vector2(p[0], p[1])), 36);
    g.computeVertexNormals();
    return new THREE.Mesh(g, new THREE.MeshStandardMaterial(
      { color, roughness: rough, metalness: 0.04, side: DS }));
  };
  // BLACK handle (flared knob -> thin handle) for the lower ~45%, then natural
  // MAPLE barrel with a gentle taper to a rounded end — matches the LS photo.
  const SPLIT = R * 0.46;
  bat.add(lathe([                                  // black handle + flared knob
    [0.000, 0.00], [0.082, 0.005], [0.098, 0.035], [0.090, 0.075],
    [0.060, 0.12], [0.044, 0.22], [0.040, R * 0.32], [0.044, SPLIT],
  ], 0x16181b, 0.5));
  bat.add(lathe([                                  // natural maple barrel + domed end
    [0.044, SPLIT], [0.052, R * 0.56], [0.070, R * 0.70], [0.098, R * 0.84],
    [0.120, R * 0.92], [0.122, R * 0.965], [0.090, R * 0.99], [0.000, R],
  ], 0xddc193, 0.45));
  world.add(bat);

  // ball that gets struck (rides the pitch in, launches out; never inside the bat)
  const ball = new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 12),
    new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0x442200, side: DS }));
  ball.position.copy(contactBall); world.add(ball);

  const center = swingCircle(curS.b, R, contact).center;        // shared rotation center
  const Y = new THREE.Vector3(0, 1, 0);
  function placeBat(phi) {
    const dir = swingCircle(curS.b, R, contact).dir(phi);       // unit center->barrel
    bat.position.copy(center);                                  // knob pinned to center
    bat.quaternion.setFromUnitVectors(Y, dir);                  // barrel end lands on the arc
  }

  // per-stage camera framing so each angle is viewed head-on (model frame; SX mirrors x):
  //   pitch = pulled back to see the ball travel the full 60'6" · aa = side profile ·
  //   tilt = catcher view · dir = top-down · contact = side · all = 3/4 at the swing.
  const CAM = {
    pitch:   { p: new THREE.Vector3(-13, 9, -16),
               t: new THREE.Vector3(0, 4, 26) },
    aa:      { p: new THREE.Vector3(-8.2, contact.y + 0.2, contact.z + 0.4),
               t: new THREE.Vector3(0, contact.y - 0.1, contact.z + 0.9) },
    tilt:    { p: new THREE.Vector3(0.4, center.y - 0.4, contact.z - 9.0),
               t: new THREE.Vector3(0, (center.y + contact.y) / 2, contact.z) },
    dir:     { p: new THREE.Vector3(0.3, 11.5, contact.z * 0.4 + 0.9),
               t: new THREE.Vector3(0, 0, contact.z * 0.4 + 0.4) },
    contact: { p: new THREE.Vector3(-9.0, 2.7, (FRONT + contact.z) / 2 + 0.3),
               t: new THREE.Vector3(0, 1.3, (FRONT + contact.z) / 2) },
    all:     { p: new THREE.Vector3(-6.4, 3.5, 5.0),
               t: new THREE.Vector3(0, 2.0, contact.z * 0.45) },
  };
  const camFor = s => { const c = CAM[s] || CAM.all;
    return { p: new THREE.Vector3(c.p.x * SX, c.p.y, c.p.z),
             t: new THREE.Vector3(c.t.x * SX, c.t.y, c.t.z) }; };

  // ===== reference-axis overlays (Savant-style reveal), grouped by ASPECT so each can
  // be isolated from the side selector. Convention to keep lines distinguishable:
  //   • the HORIZON / reference axis is DASHED + neutral
  //   • the ACTUAL measured line is SOLID + the aspect's color
  const horizRef = new THREE.Vector3(tang.x, 0, tang.z).normalize(); // travel flattened to ground
  const reveal = new THREE.Group(); reveal.visible = false; reveal.renderOrder = 10; world.add(reveal);
  const gAA = new THREE.Group(), gTilt = new THREE.Group(), gDir = new THREE.Group(),
        gCon = new THREE.Group();
  reveal.add(gAA, gTilt, gDir, gCon);
  const REF = 0xe2ebf6;                                          // neutral reference/horizon color
  const C_AA = 0xf2a73a, C_TILT = 0x5aa0ff, C_DIR = 0xc26be6, C_CON = 0x2fd7a4;
  const gDot = new THREE.Group(); reveal.add(gDot);             // contact marker (shown with "all")
  const REF_R = 0.024, ACT_R = 0.05, ARC_R = 0.034;            // tube radii: reference thin, actual thick
  const mat = (c, op = 0.97) => new THREE.MeshBasicMaterial({ color: c, transparent: true,
    opacity: op, depthTest: false, side: THREE.DoubleSide });
  function tube(g, pts, c, rad, op) {                           // real-thickness 3D line
    const geo = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts),
      Math.max(2, (pts.length - 1) * 6), rad, 12, false);
    const m = new THREE.Mesh(geo, mat(c, op)); m.renderOrder = 12; g.add(m); return m;
  }
  const ray = (g, a, b, c, rad, op) => tube(g, [a, b], c, rad, op);
  function wedge(g, anchor, u, v, r, c) {                       // angle arc between dirs u,v
    const pts = []; const n = 28;
    for (let i = 0; i <= n; i++) { const t = i / n;
      const d = u.clone().multiplyScalar(1 - t).addScaledVector(v, t).normalize();
      pts.push(anchor.clone().addScaledVector(d, r)); }
    return tube(g, pts, c, ARC_R, 0.98);
  }

  // (a) ATTACK ANGLE — at contact: thin neutral horizon baseline vs thick orange
  //     travel ray (the launch line); wedge between them = attack angle from horizontal.
  ray(gAA, contact.clone().addScaledVector(horizRef, -0.3),
          contact.clone().addScaledVector(horizRef, 2.1), REF, REF_R, 0.7);
  ray(gAA, contact.clone(), contact.clone().addScaledVector(tang, 2.1), C_AA, ACT_R);
  wedge(gAA, contact, horizRef, tang, 0.95, C_AA);

  // (b) ATTACK DIRECTION — top-down at home: thin up-the-middle axis vs thick aim ray.
  const upMid = new THREE.Vector3(0, 0, 1);
  const dirRad = (90 - cur.attack_dir) * Math.PI / 180;
  const aimDir = new THREE.Vector3(-Math.cos(dirRad), 0, Math.sin(dirRad)).normalize();
  const gy = 0.06;
  ray(gDir, new THREE.Vector3(0, gy, 0), new THREE.Vector3(0, gy, 2.6), REF, REF_R, 0.7);
  ray(gDir, new THREE.Vector3(0, gy, 0),
           new THREE.Vector3(aimDir.x * 2.6, gy, aimDir.z * 2.6), C_DIR, ACT_R);
  wedge(gDir, new THREE.Vector3(0, gy, 0), upMid, aimDir, 1.6, C_DIR);

  // (c) SWING TILT — at the KNOB: thin horizon ref vs thick blue ray down the bat;
  //     wedge between them = the tilt (down from horizontal to the bat shaft).
  const batDir = contact.clone().sub(center).normalize();
  const tiltHorizK = new THREE.Vector3(batDir.x, 0, batDir.z).normalize();
  ray(gTilt, center.clone().addScaledVector(tiltHorizK, -0.3),
            center.clone().addScaledVector(tiltHorizK, 2.1), REF, REF_R, 0.7);
  ray(gTilt, center.clone(), center.clone().addScaledVector(batDir, R), C_TILT, ACT_R);
  wedge(gTilt, center, tiltHorizK, batDir, 1.0, C_TILT);
  const tiltBisect = tiltHorizK.clone().add(batDir).normalize();

  // (d) CONTACT POINT — marker (green dot) + drop line + depth-from-plate ruler.
  const groundPt = new THREE.Vector3(contact.x, 0.05, contact.z);
  const platePt  = new THREE.Vector3(contact.x, 0.05, FRONT);
  const conMark = new THREE.Mesh(new THREE.SphereGeometry(0.13, 16, 12), mat(C_CON, 1));
  conMark.position.copy(contact); conMark.renderOrder = 13; gDot.add(conMark);  // dot stays for "all"
  ray(gCon, contact.clone(), groundPt, C_CON, REF_R, 0.85);     // drop line to ground
  ray(gCon, platePt, groundPt, C_CON, ACT_R);                   // depth ruler (plate front -> contact)
  ray(gCon, platePt.clone().setX(contact.x - 0.22), platePt.clone().setX(contact.x + 0.22), C_CON, REF_R, 0.9);
  ray(gCon, groundPt.clone().setX(contact.x - 0.22), groundPt.clone().setX(contact.x + 0.22), C_CON, REF_R, 0.9);
  const depthFront = Math.max(0, (contactZ - FRONT) / IN);

  // staged reveal: the animation steps aa -> tilt -> dir -> contact -> all, showing
  // ONE angle at a time. Clicking a selector pins one (manual). `stage` is the
  // currently-shown aspect; in "all" only the primary angle badges + dot show.
  let manual = null;                       // null = follow the auto sequence
  let stage = "aa";
  const aspectOn = a => stage === "all" || stage === a;
  let syncButtons = () => {};

  // --- floating callout labels (revealed at contact) ---
  function makeLabel(html, cls) {
    const el = document.createElement("div");
    el.className = "sw-label " + (cls || "");
    el.innerHTML = html; el.style.opacity = "0"; overlay.appendChild(el); return el;
  }
  // primary = the angle badge shown in the final "all" view; others are anchors/detail
  // that only appear in that aspect's own stage (keeps "all" to 3 non-overlapping badges).
  const labels = [
    { el: makeLabel(`<b>${cur.attack_angle.toFixed(0)}°</b><span>attack angle</span>`, "lab-aa"),
      pos: contact.clone().addScaledVector(tang, 1.25).setY(contact.y + 0.35), aspect: "aa", primary: true },
    { el: makeLabel(`<b>${cur.tilt.toFixed(0)}°</b><span>swing tilt vs horizon</span>`, "lab-tilt"),
      pos: center.clone().addScaledVector(tiltBisect, 1.45), aspect: "tilt", primary: true },
    { el: makeLabel(`<b>${cur.attack_dir >= 0 ? "+" : ""}${cur.attack_dir.toFixed(0)}°</b><span>attack direction</span>`, "lab-dir"),
      pos: new THREE.Vector3(aimDir.x * 1.75, 0.05, aimDir.z * 1.75), aspect: "dir", primary: true },
    { el: makeLabel("home", "lab-plate"), pos: new THREE.Vector3(0, 0.05, -0.95), aspect: "dir", primary: false },
    { el: makeLabel("contact", "lab-plate"), pos: contact.clone().setY(contact.y - 0.35), aspect: "aa", primary: false },
    { el: makeLabel(`<b>${depthFront.toFixed(0)}"</b><span>in front of plate</span>`, "lab-con"),
      pos: new THREE.Vector3(contact.x, 0.05, (FRONT + contactZ) / 2).setY(0.5), aspect: "contact", primary: false },
    { el: makeLabel(`<b>contact point</b><span>${depthIn.toFixed(0)}" deep · ${sideIn.toFixed(0)}" off body</span>`, "lab-con"),
      pos: contact.clone().setY(contact.y + 0.55), aspect: "contact", primary: false },
  ];
  function projectLabels(revealed) {
    const cw = renderer.domElement.clientWidth, ch = renderer.domElement.clientHeight;
    for (const L of labels) {
      const on = revealed && (stage === L.aspect || (stage === "all" && L.primary));
      const v = L.pos.clone(); v.x *= SX;            // mirror label to match the world group
      v.project(camera);
      const x = (v.x * 0.5 + 0.5) * cw, y = (-v.y * 0.5 + 0.5) * ch;
      L.el.style.opacity = (on && v.z < 1) ? "1" : "0";
      L.el.style.transform = `translate(-50%,-50%) translate(${x}px,${y}px)`;
    }
  }

  // ===== one-shot sequence: PITCH in -> CONTACT -> ball LAUNCHES along attack =====
  // Phase A (pitch+swing): ball flies in along the pitch path while the bat sweeps
  //   from load (PHI_A) into contact (phi=0); they meet at the end of A.
  // Phase B (launch): bat frozen at contact, ball flies OUT along the attack-angle
  //   ray; reference axes + angle labels fade in so you watch it leave on-angle.
  // Phase C (hold): everything freezes so you can read the angles. No loop.
  // Timeline (frames): ball travels the pitch over [0, PITCH_DUR]; the SWING is delayed
  // (starts at SWING_LEAD, arrives at contact at PITCH_DUR). After contact the reveal
  // steps through ONE angle at a time, then settles on "all". Plays once, then holds.
  const PITCH_DUR = 110, SWING_LEAD = 66, LAUNCH_DUR = 50, STAGE_DUR = 330;
  const SWING_DUR = PITCH_DUR - SWING_LEAD;
  const STAGES = ["aa", "tilt", "dir", "contact", "all"];      // reveal order
  const TOTAL = PITCH_DUR + STAGES.length * STAGE_DUR;          // ends holding on "all"
  let f = 0;
  function drawFrame(frame) {                          // render exactly one frame
    let phi = PHI_A, revealed = false;                 // bat waits at load by default
    if (frame < PITCH_DUR) {
      ball.visible = true;
      ball.position.copy(pitchPos(frame / PITCH_DUR)); ball.scale.setScalar(1);
      pitchLine.visible = true; launchLine.visible = false; reveal.visible = false;
      curS.grp.visible = true; adjS.grp.visible = false;   // show the plane during the swing
      if (frame >= SWING_LEAD) {
        const s = (frame - SWING_LEAD) / SWING_DUR, e = s * s * (3 - 2 * s);
        phi = PHI_A * (1 - e);                          // load -> contact (phi=0)
      }
    } else {
      // contact made: bat frozen; step through one angle at a time (or pinned manual)
      phi = 0; revealed = true; reveal.visible = true;
      const t = frame - PITCH_DUR;
      const si = Math.min(Math.floor(t / STAGE_DUR), STAGES.length - 1);
      stage = manual || STAGES[si];
      // hide the busy swing-plane disc/rings while isolating one angle; show in "all"
      curS.grp.visible = (stage === "all"); adjS.grp.visible = (stage === "all");
      gAA.visible = aspectOn("aa"); gTilt.visible = aspectOn("tilt");
      gDir.visible = aspectOn("dir");
      gCon.visible = (stage === "contact");           // ruler only in its own stage
      gDot.visible = (stage === "contact" || stage === "all");  // dot also marks contact in "all"
      // ball launches along the attack angle during the FIRST stage, then rests;
      // it only shows in the attack-angle and "all" views.
      ball.position.copy(launchPos(Math.min(t, LAUNCH_DUR) / LAUNCH_DUR));
      const showAA = (stage === "aa" || stage === "all");
      ball.visible = showAA; launchLine.visible = showAA; pitchLine.visible = showAA;
      ball.scale.setScalar(1 + 0.7 * Math.max(0, 1 - t / 8));
      syncButtons();
    }
    placeBat(phi);
    if (camMode === "auto") {                          // rotate to frame the current angle
      const c = camFor(revealed ? stage : "pitch");    // pulled back during the pitch
      camera.position.lerp(c.p, 0.05);                 // slow, smooth re-orient
      controls.target.lerp(c.t, 0.05);
    }
    controls.update(); renderer.render(scene, camera);
    projectLabels(revealed);
  }
  function animate() {
    drawFrame(f);
    if (f < TOTAL) f++;                               // play once, then hold
    _state.raf = requestAnimationFrame(animate);
  }
  // side selector — pin a single angle (manual), or "All angles" to show the clean set.
  const ASPECTS = [["aa", "Attack angle"], ["tilt", "Swing tilt"],
                   ["dir", "Attack direction"], ["contact", "Contact point"],
                   ["all", "All angles"]];
  const panel = document.createElement("div"); panel.className = "sw-aspects";
  const aBtns = {};
  for (const [key, label] of ASPECTS) {
    const b = document.createElement("button"); b.type = "button"; b.textContent = label;
    b.className = "sw-aspect"; b.dataset.key = key;
    b.onclick = () => { manual = key; stage = key; camMode = "auto";
      if (f < PITCH_DUR) f = PITCH_DUR; drawFrame(f); }; // pin + re-orient + refresh
    panel.appendChild(b); aBtns[key] = b;
  }
  container.appendChild(panel);
  syncButtons = () => {                                // highlight the active stage
    for (const k in aBtns) aBtns[k].classList.toggle("on", k === stage);
  };
  // replay button — re-runs the whole guided sequence from the top
  const replayBtn = document.createElement("button");
  replayBtn.className = "sw-replay"; replayBtn.type = "button";
  replayBtn.innerHTML = "&#x21bb; Replay";
  replayBtn.onclick = () => { manual = null; f = 0; camMode = "auto"; drawFrame(0); };
  container.appendChild(replayBtn);
  const onResize = () => { const w = container.clientWidth || W;
    renderer.setSize(w, H); camera.aspect = w / H; camera.updateProjectionMatrix(); };
  _state = { renderer, controls, raf: 0, onResize, overlay, replayBtn, panel, drawFrame, TOTAL,
    seek: n => { f = Math.max(0, Math.min(TOTAL, n)); drawFrame(f); },
    setAspect: k => { manual = k; stage = k; camMode = "auto"; if (f < PITCH_DUR) f = PITCH_DUR; drawFrame(f); },
    replay: () => { manual = null; f = 0; camMode = "auto"; } };
  window.addEventListener("resize", onResize);
  window.__swingState = _state;                        // debug hook (seek/replay/setAspect)
  animate();
}

window.renderSwing3D = renderSwing3D;
window.disposeSwing3D = disposeSwing3D;
