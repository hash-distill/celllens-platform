import * as THREE from 'three';

/**
 * CellLens illustrative cutaway cell. Geometry is schematic, not image-derived.
 * No external assets, textures, network requests, or biological predictions.
 */
export function mountCellScene(container, { onSelect = () => {}, compact = false, interactive = true, onUnavailable = () => {}, onZoomChange = () => {} } = {}) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, premultipliedAlpha: false, powerPreference: 'low-power' });
  } catch {
    return null;
  }

  const canvas = renderer.domElement;
  canvas.setAttribute('aria-label', '细胞结构示意。拖动旋转，Ctrl 加滚轮缩放，点击选择；也可使用下方按钮。');
  canvas.setAttribute('role', 'img');
  Object.assign(canvas.style, { width: '100%', height: '100%', display: 'block', cursor: 'grab', touchAction: 'pan-y' });
  container.append(canvas);
  renderer.setClearColor(0x000000, 0);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.65));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.35;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 50);
  camera.position.set(0, 0.14, compact ? 11.2 : 10.4);
  camera.lookAt(0, 0, 0);
  scene.add(new THREE.HemisphereLight(0xe2fff2, 0x0e382c, 2.3));
  const keyLight = new THREE.DirectionalLight(0xf0ffe7, 4.1);
  keyLight.position.set(-4, 5, 7);
  scene.add(keyLight);
  const rimLight = new THREE.DirectionalLight(0x5cddb5, 2.8);
  rimLight.position.set(4, 1, -4);
  scene.add(rimLight);
  const fillLight = new THREE.DirectionalLight(0xe2b76e, 1.35);
  fillLight.position.set(1, -4, 4);
  scene.add(fillLight);

  const cell = new THREE.Group();
  cell.rotation.set(0.09, -0.18, -0.1);
  scene.add(cell);
  const pickable = [];
  const groups = {};
  const materialBaseline = new Map();
  const tubeGeometries = [];
  const rand = seeded(72841);
  const v = (x, y, z) => new THREE.Vector3(x, y, z);

  function material(color, options = {}) {
    const m = new THREE.MeshPhysicalMaterial({ color, roughness: 0.4, metalness: 0.08, clearcoat: 0.6, clearcoatRoughness: 0.22, ...options });
    return m;
  }
  function group(key) {
    const g = new THREE.Group(); g.userData.key = key; cell.add(g); groups[key] = g; return g;
  }
  function addMesh(geometry, mat, parent, key) {
    const mesh = new THREE.Mesh(geometry, mat);
    parent.add(mesh);
    if (key) { mesh.userData.key = key; pickable.push(mesh); }
    if (mat.emissive) materialBaseline.set(mat, { color: mat.emissive.clone(), intensity: mat.emissiveIntensity });
    return mesh;
  }
  function tube(points, radius, color, parent, options = {}) {
    const path = new THREE.CatmullRomCurve3(points);
    const geometry = new THREE.TubeGeometry(path, Math.max(24, points.length * 4), radius, 5, false);
    tubeGeometries.push(geometry);
    const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color, roughness: 0.48, metalness: 0.1, ...options }));
    parent.add(mesh); return mesh;
  }

  // Back shell and thick rolled edge: a large opening preserves the organelle view.
  const membrane = group('membrane');
  const shellGeometry = ellipsoidShell(0.86, Math.PI, 96, 40);
  const shell = addMesh(shellGeometry, material(0x6ce1ae, {
    transparent: true, opacity: 0.19, depthWrite: false, side: THREE.DoubleSide,
    roughness: 0.3, metalness: 0.04, clearcoat: 1,
    emissive: 0x126541, emissiveIntensity: 0.2
  }), membrane, 'membrane');
  shell.renderOrder = 1;

  // Fresnel rim makes the cutaway read as a membrane rather than a wire sphere.
  const glow = new THREE.Mesh(ellipsoidShell(0.855, Math.PI, 80, 28), new THREE.ShaderMaterial({
    uniforms: { uColor: { value: new THREE.Color(0x86f6c2) } },
    vertexShader: 'varying vec3 vN; varying vec3 vV; void main(){vec4 mv=modelViewMatrix*vec4(position,1.);vN=normalize(normalMatrix*normal);vV=normalize(-mv.xyz);gl_Position=projectionMatrix*mv;}',
    fragmentShader: 'uniform vec3 uColor;varying vec3 vN;varying vec3 vV;void main(){float f=pow(1.-abs(dot(normalize(vN),normalize(vV))),2.5);gl_FragColor=vec4(uColor,.025+f*.36);}',
    transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending
  }));
  glow.scale.setScalar(1.004); glow.renderOrder = 6; membrane.add(glow);
  for (let j = 0; j < 3; j++) {
    const points = [];
    for (let i = 0; i <= 120; i++) points.push(surfacePoint(0.86 + j * 0.019, i / 120 * Math.PI * 2));
    tube(points, j === 0 ? 0.026 : 0.012, j === 0 ? 0xb8f2c9 : 0x54bd93, membrane, { transparent: true, opacity: j === 0 ? 0.85 : 0.6 });
  }
  // Subtle longitudinal folds on the far membrane.
  for (let n = 0; n < 9; n++) {
    const pts = [];
    for (let i = 0; i <= 22; i++) pts.push(surfacePoint(0.88 + i / 22 * 1.8, n / 9 * Math.PI * 2));
    tube(pts, 0.007, 0x8cd6b3, membrane, { transparent: true, opacity: 0.24 });
  }

  // Nucleus with a translucent envelope, chromatin and nucleolus.
  const nucleus = group('nucleus');
  nucleus.position.set(-0.34, 0.18, 0.34);
  const nuclearCore = addMesh(new THREE.SphereGeometry(0.9, 52, 36), material(0x237b77, {
    roughness: 0.26, metalness: 0.12, emissive: 0x0d5148, emissiveIntensity: 0.26
  }), nucleus, 'nucleus');
  nuclearCore.scale.set(1.02, 0.94, 0.85);
  const envelope = addMesh(new THREE.SphereGeometry(0.97, 52, 36), material(0x78d9c4, {
    transparent: true, opacity: 0.23, depthWrite: false, roughness: 0.2, clearcoat: 1,
    emissive: 0x1c7968, emissiveIntensity: 0.15
  }), nucleus, 'nucleus');
  envelope.scale.set(1.02, 0.94, 0.85); envelope.renderOrder = 3;
  const nucleolus = addMesh(new THREE.SphereGeometry(0.25, 32, 24), material(0xd3e7ac, { roughness: 0.31, metalness: 0.1 }), nucleus, 'nucleus');
  nucleolus.position.set(-0.15, 0.15, 0.73); nucleolus.scale.set(1.05, 0.83, 0.58);
  for (let k = 0; k < 7; k++) {
    const points = [];
    const angle = k * 0.85;
    for (let i = 0; i < 22; i++) {
      const a = i / 21 * 2.65 + angle;
      const r = 0.45 + k * 0.042;
      points.push(v(Math.cos(a) * r, Math.sin(a) * r * 0.8, 0.56 + Math.sin(a * 3 + k) * 0.08));
    }
    tube(points, 0.012, k % 2 ? 0x9bd8bb : 0x4fb9a8, nucleus, { transparent: true, opacity: 0.72 });
  }
  const poreGeo = new THREE.TorusGeometry(0.034, 0.009, 6, 12);
  const poreMat = material(0xbedfc0, { roughness: 0.5 });
  for (let i = 0; i < 37; i++) {
    const phi = i * 2.399963;
    const z = 0.18 + (i / 37) * 0.76;
    const rr = Math.sqrt(1 - z * z);
    const dir = v(rr * Math.cos(phi), rr * Math.sin(phi), z);
    const pore = new THREE.Mesh(poreGeo, poreMat);
    pore.position.copy(dir).multiply(v(0.99, 0.91, 0.83));
    pore.quaternion.setFromUnitVectors(v(0, 0, 1), dir.normalize()); nucleus.add(pore);
  }

  // Smooth bean-shaped mitochondria with visible inner-membrane cristae.
  const mitochondria = group('mitochondria');
  const mitochondrialPositions = [
    [1.53, 0.63, 0.58, -0.5, 0.81], [-1.62, 0.76, 0.38, 0.75, 0.71],
    [-1.48, -0.91, 0.67, -0.64, 0.8], [1.38, -0.8, 0.65, 0.66, 0.87],
    [0.17, -1.34, 0.26, -0.14, 0.55], [0.49, 1.37, 0.0, 0.3, 0.59],
    [2.05, -0.17, -0.1, 1.12, 0.52]
  ];
  mitochondrialPositions.forEach((p, idx) => {
    const organelle = new THREE.Group(); organelle.position.set(p[0], p[1], p[2]); organelle.rotation.set(0.1 * (idx - 2), -0.13, p[3]); organelle.scale.setScalar(p[4]); mitochondria.add(organelle);
    const outer = addMesh(beanGeometry(), material(idx % 3 === 0 ? 0xd9ae65 : 0xc99351, {
      roughness: 0.43, metalness: 0.1, emissive: 0x5b3e18, emissiveIntensity: 0.1
    }), organelle, 'mitochondria');
    const crest = [];
    for (let i = 0; i <= 70; i++) {
      const t = i / 70;
      const x = (t - 0.5) * 1.18;
      const taper = Math.sin(Math.PI * t);
      crest.push(v(x, 0.12 * Math.cos(t * Math.PI * 1.2) + Math.sin(t * Math.PI * 12) * 0.135 * taper, 0.205 + 0.04 * taper));
    }
    tube(crest, 0.024, 0xf3d79a, organelle);
    const outerRim = [];
    for (let i = 0; i <= 50; i++) {
      const a = i / 50 * Math.PI * 2;
      outerRim.push(v(Math.cos(a) * 0.61, Math.sin(a) * 0.19 + 0.12 * Math.cos((Math.cos(a) + 1) * 0.6 * Math.PI), 0.15));
    }
    tube(outerRim, 0.013, 0xefd3a0, organelle, { transparent: true, opacity: 0.7 });
  });

  // A ribbed, folded ER fan around the nucleus, placed behind the front organelles.
  const er = group('er');
  const erMats = [material(0x6bb496, { roughness: 0.48, side: THREE.DoubleSide }), material(0x419b88, { roughness: 0.4, side: THREE.DoubleSide })];
  for (let k = 0; k < 7; k++) {
    const ribbon = addMesh(ribbonGeometry(k), erMats[k % 2], er, 'er');
    const edge = [];
    for (let i = 0; i <= 64; i++) edge.push(ribbonPoint(k, i / 64, 1));
    tube(edge, 0.013, 0xb9dcb1, er, { transparent: true, opacity: 0.78 });
    for (let n = 0; n < 8; n++) {
      const point = ribbonPoint(k, (n + 0.4) / 8, 0.5);
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.022, 6, 4), material(0xd4dcb4));
      dot.position.copy(point).add(v(0, 0, 0.035)); er.add(dot);
    }
  }

  // Flattened Golgi cisternae provide a distinct, selectable structure region.
  const golgi = group('golgi');
  golgi.position.set(0.22, -0.95, 0.45);
  golgi.rotation.z = -0.15;
  for (let k = 0; k < 5; k++) {
    const points = [];
    for (let i = 0; i <= 24; i++) {
      const t = i / 24;
      points.push(v((t - 0.5) * (1.07 - k * 0.08), -k * 0.085 + Math.sin(t * Math.PI) * 0.16, k * 0.025));
    }
    const g = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 28, 0.048, 6, false);
    addMesh(g, material(k % 2 ? 0xd8b8a1 : 0xb88d7b, { roughness: 0.48 }), golgi, 'golgi');
  }
  const cytoplasm = group('cytoplasm');

  // Cytoskeletal arcs and ribosomes: visual context with restrained density.
  const filaments = new THREE.Group(); cytoplasm.add(filaments);
  for (let k = 0; k < 9; k++) {
    const a = k / 9 * Math.PI * 2;
    const pts = [];
    for (let i = 0; i <= 22; i++) {
      const t = i / 22;
      pts.push(v(Math.cos(a + t * 0.55) * (0.9 + t * 1.45), Math.sin(a + t * 0.55) * (0.6 + t * 1.1), -0.43 + Math.sin(t * Math.PI) * 0.22));
    }
    tube(pts, 0.009, k % 2 ? 0x8cbf87 : 0x4fa989, filaments, { transparent: true, opacity: 0.54 });
  }
  const particleGeo = new THREE.SphereGeometry(0.025, 7, 5);
  const particleMat = material(0xc1dab0, { roughness: 0.6 });
  materialBaseline.set(particleMat, { color: particleMat.emissive.clone(), intensity: particleMat.emissiveIntensity });
  const particles = new THREE.InstancedMesh(particleGeo, particleMat, compact ? 85 : 145);
  const dummy = new THREE.Object3D();
  for (let i = 0; i < particles.count; i++) {
    let p;
    do {
      p = v((rand() - 0.5) * 4.9, (rand() - 0.5) * 3.55, (rand() - 0.5) * 2.0);
    } while ((p.x / 2.5) ** 2 + (p.y / 1.8) ** 2 + (p.z / 1.1) ** 2 > 1 || p.distanceTo(nucleus.position) < 1.1);
    dummy.position.copy(p); dummy.scale.setScalar(0.5 + rand() * 0.9); dummy.updateMatrix(); particles.setMatrixAt(i, dummy.matrix);
  }
  particles.userData.key = 'cytoplasm'; pickable.push(particles); cytoplasm.add(particles);

  // Fine, detached orientation ring gives the visualization an instrument-like frame.
  const instrument = new THREE.Group(); scene.add(instrument);
  const ringPoints = [];
  for (let i = 0; i <= 180; i++) {
    const a = i / 180 * Math.PI * 2;
    ringPoints.push(v(Math.cos(a) * 3.18, Math.sin(a) * 2.27, -0.5));
  }
  const ringGeo = new THREE.BufferGeometry().setFromPoints(ringPoints);
  const ring = new THREE.Line(ringGeo, new THREE.LineDashedMaterial({ color: 0x89c5aa, transparent: true, opacity: 0.23, dashSize: 0.025, gapSize: 0.055 }));
  ring.computeLineDistances(); instrument.add(ring);

  let disposed = false, frame = 0, last = 0, elapsed = 0;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  let playing = !reduced.matches;
  let inView = true;
  let selected = '', dragging = false, moved = false, pointerId = null, lastX = 0, lastY = 0;
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const originalRotation = cell.rotation.clone();
  const targets = { x: originalRotation.x, y: originalRotation.y };

  function select(key, notify = false) {
    selected = groups[key] ? key : '';
    for (const [m, base] of materialBaseline) { m.emissive.copy(base.color); m.emissiveIntensity = base.intensity; }
    if (selected) groups[selected].traverse(object => {
      const m = object.material;
      if (m?.emissive && materialBaseline.has(m)) { m.emissive.set(selected === 'mitochondria' ? 0xc08831 : 0x43bd91); m.emissiveIntensity = 0.4; }
    });
    render();
    if (notify && selected) onSelect(selected);
  }
  function resize() {
    if (disposed) return;
    const rect = container.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    renderer.setSize(rect.width, rect.height, false);
    camera.aspect = rect.width / rect.height;
    camera.position.z = Math.max(compact ? 8.0 : 9.9, (compact ? 8.6 : 10.7) / camera.aspect);
    camera.updateProjectionMatrix(); render();
  }
  function render() { if (!disposed) renderer.render(scene, camera); }
  function animate(now) {
    if (disposed) return;
    frame = requestAnimationFrame(animate);
    if (!inView || document.hidden || now - last < 32) return;
    const dt = Math.min((now - last) / 1000, 0.05); last = now;
    if (!playing && !dragging && Math.abs(targets.x - cell.rotation.x) + Math.abs(targets.y - cell.rotation.y) < 0.0001) return;
    if (playing && !dragging) elapsed += dt;
    cell.rotation.x += (targets.x + (playing ? Math.sin(elapsed * 0.25) * 0.045 : 0) - cell.rotation.x) * 0.12;
    cell.rotation.y += (targets.y + (playing ? Math.sin(elapsed * 0.19) * 0.1 : 0) - cell.rotation.y) * 0.12;
    if (playing) cell.position.y = Math.sin(elapsed * 0.55) * 0.04;
    render();
  }
  function pick(event) {
    const rect = canvas.getBoundingClientRect();
    pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(pickable, false);
    // The translucent shell must never intercept a nearer opaque organelle.
    return hits.find(hit => hit.object.userData.key !== 'membrane') || hits[0];
  }
  function down(event) {
    if (!interactive || event.button !== 0) return;
    dragging = true; moved = false; pointerId = event.pointerId;
    lastX = event.clientX; lastY = event.clientY;
    canvas.setPointerCapture(pointerId); canvas.style.cursor = 'grabbing';
  }
  function move(event) {
    if (!interactive) return;
    if (!dragging) { canvas.style.cursor = pick(event) ? 'pointer' : 'grab'; return; }
    const dx = event.clientX - lastX, dy = event.clientY - lastY;
    if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
    targets.y += dx * 0.005; targets.x = Math.max(-0.75, Math.min(0.75, targets.x + dy * 0.004));
    lastX = event.clientX; lastY = event.clientY;
  }
  function up(event) {
    if (!dragging) return;
    dragging = false; canvas.style.cursor = 'grab';
    if (pointerId !== null && canvas.hasPointerCapture(pointerId)) canvas.releasePointerCapture(pointerId);
    pointerId = null;
    if (!moved && event.type !== 'pointercancel') { const hit = pick(event); if (hit) select(hit.object.userData.key, true); }
  }
  function setZoom(value) {
    if (disposed || !Number.isFinite(value)) return camera.zoom;
    camera.zoom = Math.max(0.65, Math.min(1.6, value));
    camera.updateProjectionMatrix(); render(); onZoomChange(camera.zoom);
    return camera.zoom;
  }
  function wheel(event) {
    if (!interactive || !event.ctrlKey) return;
    event.preventDefault(); setZoom(camera.zoom * Math.exp(-event.deltaY * 0.002));
  }
  canvas.addEventListener('pointerdown', down); canvas.addEventListener('pointermove', move);
  canvas.addEventListener('pointerup', up); canvas.addEventListener('pointercancel', up);
  canvas.addEventListener('wheel', wheel, { passive: false });
  const visibility = new IntersectionObserver(entries => { inView = entries.some(entry => entry.isIntersecting); }); visibility.observe(container);
  function contextLost(event) { event.preventDefault(); onUnavailable(); }
  canvas.addEventListener('webglcontextlost', contextLost);
  const observer = new ResizeObserver(resize); observer.observe(container);
  resize(); frame = requestAnimationFrame(animate);

  return {
    select(key) { select(key); },
    reset() { targets.x = originalRotation.x; targets.y = originalRotation.y; cell.rotation.copy(originalRotation); cell.position.y = 0; elapsed = 0; setZoom(1); resize(); },
    setZoom,
    toggleMotion() { playing = !playing; return playing; },
    setMotion(value) { playing = value; },
    dispose() {
      if (disposed) return; disposed = true; cancelAnimationFrame(frame); observer.disconnect(); visibility.disconnect();
      canvas.removeEventListener('webglcontextlost', contextLost);
      canvas.removeEventListener('pointerdown', down); canvas.removeEventListener('pointermove', move);
      canvas.removeEventListener('pointerup', up); canvas.removeEventListener('pointercancel', up);
      canvas.removeEventListener('wheel', wheel);
      const geometries = new Set(), materials = new Set();
      scene.traverse(object => { if (object.geometry) geometries.add(object.geometry); if (object.material) (Array.isArray(object.material) ? object.material : [object.material]).forEach(m => materials.add(m)); });
      geometries.forEach(g => g.dispose()); materials.forEach(m => m.dispose()); renderer.dispose(); renderer.forceContextLoss(); canvas.remove();
    }
  };
}

function seeded(seed) { return () => { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 4294967296; }; }

function surfacePoint(theta, phi) {
  const r = 1 + 0.045 * Math.sin(phi * 3 + theta) + 0.025 * Math.cos(phi * 5 - theta * 2);
  return new THREE.Vector3(2.78 * Math.sin(theta) * Math.cos(phi) * r, 2.0 * Math.sin(theta) * Math.sin(phi) * r, 1.4 * Math.cos(theta) * r);
}

function ellipsoidShell(start, end, columns, rows) {
  const points = [], indices = [];
  for (let j = 0; j <= rows; j++) for (let i = 0; i <= columns; i++) {
    const p = surfacePoint(start + (end - start) * j / rows, i / columns * Math.PI * 2);
    points.push(p.x, p.y, p.z);
  }
  for (let j = 0; j < rows; j++) for (let i = 0; i < columns; i++) {
    const a = j * (columns + 1) + i, b = a + columns + 1;
    indices.push(a, b, a + 1, b, b + 1, a + 1);
  }
  const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3)); geometry.setIndex(indices); geometry.computeVertexNormals(); return geometry;
}

function beanGeometry() {
  const points = [], indices = []; const steps = 40, sides = 16;
  for (let j = 0; j <= steps; j++) {
    const t = j / steps, r = 0.23 * Math.pow(Math.sin(Math.PI * t), 0.48);
    for (let i = 0; i <= sides; i++) {
      const a = i / sides * Math.PI * 2;
      points.push((t - 0.5) * 1.45, 0.12 * Math.cos(t * Math.PI * 1.2) + Math.sin(a) * r, Math.cos(a) * r * 0.88);
    }
  }
  for (let j = 0; j < steps; j++) for (let i = 0; i < sides; i++) {
    const a = j * (sides + 1) + i, b = a + sides + 1;
    indices.push(a, b, a + 1, b, b + 1, a + 1);
  }
  const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3)); geometry.setIndex(indices); geometry.computeVertexNormals(); return geometry;
}

function ribbonPoint(k, t, side) {
  const angle = -0.2 + t * 2.35;
  const radius = 1.04 + k * 0.1 + side * 0.065;
  return new THREE.Vector3(-0.38 + Math.cos(angle) * radius, 0.19 + Math.sin(angle) * radius * 0.85, -0.04 + Math.sin(t * Math.PI * 5 + k * 0.5) * 0.095 - k * 0.04 + side * 0.07);
}

function ribbonGeometry(k) {
  const points = [], indices = [], n = 64;
  for (let i = 0; i <= n; i++) for (let j = 0; j < 2; j++) { const p = ribbonPoint(k, i / n, j); points.push(p.x, p.y, p.z); }
  for (let i = 0; i < n; i++) { const a = i * 2; indices.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
  const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3)); geometry.setIndex(indices); geometry.computeVertexNormals(); return geometry;
}
