import * as THREE from 'three'
import type { OrganelleId } from '../stores/scene'

export interface CellModel {
  root: THREE.Group
  groups: Record<OrganelleId, THREE.Group>
  anchors: Record<OrganelleId, THREE.Vector3>
  membrane: THREE.MeshPhysicalMaterial
  cutPlane: THREE.Plane
  cutRim: THREE.LineLoop
  select: (id: OrganelleId) => void
  setCut: (enabled: boolean, position: number) => void
  dispose: () => void
}

const colors = { membrane: '#87b5aa', nucleus: '#9d8caf', mitochondria: '#bb955c', er: '#62899e', golgi: '#c8957b' }

function surface(color: string, extra: THREE.MeshStandardMaterialParameters = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.48, metalness: 0.1, ...extra })
}

function tube(points: THREE.Vector3[], radius: number, material: THREE.Material, closed = false) {
  return new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points, closed), Math.max(24, points.length * 3), radius, 5, closed), material)
}

// An authored membrane sheet, folded along a circular arc. All geometry is deterministic.
function ribbon(radius: number, start: number, end: number, width: number, wave: number) {
  const positions: number[] = []
  const indices: number[] = []
  const steps = 72
  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps
    const a = start + (end - start) * t
    for (let j = 0; j <= 4; j += 1) {
      const w = (j / 4 - 0.5) * width
      const r = radius + w + 0.075 * Math.sin(a * 7)
      positions.push(Math.cos(a) * r, Math.sin(a) * r * 0.88, wave * Math.sin(a * 4 + j * 0.28) + 0.1 * Math.cos(a * 2))
      if (i < steps && j < 4) {
        const k = i * 5 + j
        indices.push(k, k + 5, k + 1, k + 1, k + 5, k + 6)
      }
    }
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setIndex(indices)
  geometry.computeVertexNormals()
  return geometry
}

export function createCellModel(): CellModel {
  const root = new THREE.Group()
  const groups = {} as Record<OrganelleId, THREE.Group>
  for (const id of Object.keys(colors) as OrganelleId[]) {
    const group = new THREE.Group()
    group.name = id
    group.userData.organelle = id
    groups[id] = group
    root.add(group)
  }
  const anchors = {
    membrane: new THREE.Vector3(-3.05, 1.45, 0.5),
    nucleus: new THREE.Vector3(-0.6, 0.62, 1.35),
    mitochondria: new THREE.Vector3(2.24, 1.04, 0.72),
    er: new THREE.Vector3(-1.62, -1.29, 0.72),
    golgi: new THREE.Vector3(1.48, -1.72, 1.12),
  }
  const cutPlane = new THREE.Plane(new THREE.Vector3(0, 0, -1), 0.8)
  const membrane = new THREE.MeshPhysicalMaterial({
    color: colors.membrane, roughness: 0.3, metalness: 0.06,
    transparent: true, opacity: 0.32, side: THREE.DoubleSide, depthWrite: false,
    clearcoat: 0.38, clearcoatRoughness: 0.42, clippingPlanes: [cutPlane],
  })
  const membraneGeometry = new THREE.SphereGeometry(1, 80, 48)
  const p = membraneGeometry.attributes.position!
  for (let i = 0; i < p.count; i += 1) {
    const x = p.getX(i), y = p.getY(i), z = p.getZ(i)
    const rough = 1 + 0.018 * Math.sin(x * 19 + y * 11) * Math.cos(z * 13) + 0.025 * Math.sin(y * 8 + z * 7)
    p.setXYZ(i, x * 3.6 * rough, y * 3.0 * rough, z * 2.5 * rough)
  }
  membraneGeometry.computeVertexNormals()
  const shell = new THREE.Mesh(membraneGeometry, membrane)
  shell.renderOrder = 8
  groups.membrane.add(shell)
  const cutRim = new THREE.LineLoop(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: '#b8d5ca', transparent: true, opacity: 0.75 }))
  groups.membrane.add(cutRim)

  const nucleusMaterial = surface(colors.nucleus, { transparent: true, opacity: 0.77, side: THREE.DoubleSide, depthWrite: false, roughness: 0.65 })
  const nucleus = new THREE.Mesh(new THREE.SphereGeometry(1.18, 48, 32), nucleusMaterial)
  nucleus.position.set(-0.58, 0.32, 0.2)
  nucleus.scale.set(1.02, 1.05, 0.95)
  groups.nucleus.add(nucleus)
  const nucleolus = new THREE.Mesh(new THREE.SphereGeometry(0.36, 28, 20), surface('#756c91', { roughness: 0.82 }))
  nucleolus.position.set(-0.68, 0.17, 1.03)
  groups.nucleus.add(nucleolus)
  const chromatinMaterial = surface('#c3b5d2', { transparent: true, opacity: 0.65, roughness: 0.8 })
  for (let strand = 0; strand < 20; strand += 1) {
    const points: THREE.Vector3[] = []
    for (let j = 0; j <= 38; j += 1) {
      const t = j / 38 * Math.PI * 2
      const a = t + strand * 0.91
      const rad = 0.68 + 0.2 * Math.sin(t * 3 + strand)
      points.push(new THREE.Vector3(-0.58 + Math.cos(a) * rad, 0.32 + Math.sin(a) * rad, 0.2 + Math.sin(t * 2 + strand * 0.5) * 0.52))
    }
    groups.nucleus.add(tube(points, 0.012, chromatinMaterial))
  }

  const erMaterial = surface(colors.er, { side: THREE.DoubleSide, roughness: 0.45 })
  const erEdgeMaterial = surface('#aac1ce', { roughness: 0.55 })
  for (let layer = 0; layer < 8; layer += 1) {
    const rad = 1.42 + layer * 0.13
    const start = -Math.PI * 0.12 + layer * 0.08
    const end = Math.PI * (1.78 - layer * 0.025)
    const sheet = new THREE.Mesh(ribbon(rad, start, end, 0.24, 0.16), erMaterial)
    sheet.position.set(-0.6, 0.3, 0.12 + layer * 0.05)
    sheet.rotation.x = 0.1 * Math.sin(layer)
    groups.er.add(sheet)
    const edge: THREE.Vector3[] = []
    for (let i = 0; i <= 65; i += 1) {
      const a = start + (end - start) * i / 65
      const r = rad + 0.12 + 0.075 * Math.sin(a * 7)
      edge.push(new THREE.Vector3(Math.cos(a) * r, Math.sin(a) * r * 0.88, 0.16 * Math.sin(a * 4 + 1.12) + 0.1 * Math.cos(a * 2)))
    }
    const seam = tube(edge, 0.024, erEdgeMaterial)
    seam.position.copy(sheet.position)
    seam.rotation.copy(sheet.rotation)
    groups.er.add(seam)
  }

  const mitochondriaMaterial = surface(colors.mitochondria, { side: THREE.DoubleSide, roughness: 0.4, metalness: 0.17 })
  const innerMaterial = surface('#d8b573', { roughness: 0.5, metalness: 0.13 })
  const mitoPositions = [
    [2.18, 1.06, 0.58, -0.78, 0.95], [1.13, 2.01, -0.22, -0.32, 0.68],
    [-2.04, -1.66, 0.6, -0.53, 0.83], [0.35, -2.17, 0.32, -0.24, 0.85],
    [2.64, -0.92, -0.11, -1.0, 0.65], [-2.24, 1.31, -0.5, 0.7, 0.73],
  ]
  for (const values of mitoPositions) {
    const [x = 0, y = 0, z = 0, angle = 0, size = 1] = values
    const organelle = new THREE.Group()
    organelle.position.set(x, y, z)
    organelle.rotation.set(0.15, -0.12, angle)
    organelle.scale.setScalar(size)
    const outer = new THREE.Mesh(new THREE.SphereGeometry(1, 36, 22, Math.PI, Math.PI), mitochondriaMaterial)
    outer.scale.set(0.85, 0.37, 0.34)
    organelle.add(outer)
    const lip: THREE.Vector3[] = []
    for (let i = 0; i < 64; i += 1) {
      const a = i / 64 * Math.PI * 2
      lip.push(new THREE.Vector3(Math.cos(a) * 0.85, Math.sin(a) * 0.37, 0))
    }
    organelle.add(tube(lip, 0.033, innerMaterial, true))
    // Interior folds are separate curves, visible through the open outer membrane.
    for (let fold = 0; fold < 8; fold += 1) {
      const fx = -0.62 + fold * 0.175
      const height = 0.3 * Math.sqrt(Math.max(0, 1 - (fx / 0.8) ** 2))
      const points: THREE.Vector3[] = []
      for (let j = 0; j <= 14; j += 1) {
        const t = j / 14
        points.push(new THREE.Vector3(fx + 0.09 * Math.sin(t * Math.PI * 2), (t * 2 - 1) * height, -0.12 + 0.13 * Math.sin(t * Math.PI)))
      }
      organelle.add(tube(points, 0.032, innerMaterial))
    }
    groups.mitochondria.add(organelle)
  }

  const golgiMaterial = surface(colors.golgi, { side: THREE.DoubleSide, roughness: 0.45 })
  const golgiEdge = surface('#e3b99c', { roughness: 0.6 })
  for (let layer = 0; layer < 7; layer += 1) {
    const r = 0.79 + layer * 0.035
    const sheet = new THREE.Mesh(ribbon(r, Math.PI * 1.09, Math.PI * 1.92, 0.28, 0.055), golgiMaterial)
    sheet.position.set(1.33, -1.2 + layer * 0.12, 0.7 + layer * 0.09)
    sheet.rotation.z = 0.22
    sheet.scale.set(1.1, 0.64, 1)
    groups.golgi.add(sheet)
    const seam: THREE.Vector3[] = []
    for (let j = 0; j <= 36; j += 1) {
      const a = Math.PI * (1.09 + 0.83 * j / 36)
      seam.push(new THREE.Vector3(Math.cos(a) * (r + 0.14), Math.sin(a) * (r + 0.14) * 0.88, 0.055 * Math.sin(a * 4 + 1.12) + 0.1 * Math.cos(a * 2)))
    }
    const edge = tube(seam, 0.025, golgiEdge)
    edge.position.copy(sheet.position)
    edge.rotation.copy(sheet.rotation)
    edge.scale.copy(sheet.scale)
    groups.golgi.add(edge)
  }
  const vesicleGeometry = new THREE.SphereGeometry(0.1, 14, 10)
  for (let i = 0; i < 14; i += 1) {
    const vesicle = new THREE.Mesh(vesicleGeometry, golgiMaterial)
    const a = i * 2.39
    vesicle.position.set(1.25 + Math.cos(a) * (0.9 + (i % 3) * 0.1), -1.18 + Math.sin(a) * 0.58, 0.63 + (i % 4) * 0.16)
    vesicle.scale.setScalar(0.6 + (i % 3) * 0.22)
    groups.golgi.add(vesicle)
  }

  const ribosomes = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(0.027, 0), surface('#d0b894', { roughness: 0.8 }), 230)
  const dummy = new THREE.Object3D()
  for (let i = 0; i < 230; i += 1) {
    const a = i * 2.39996
    const r = 1.45 + (i % 17) / 17 * 0.94
    dummy.position.set(-0.55 + Math.cos(a) * r, 0.3 + Math.sin(a) * r * 0.86, 0.32 + Math.sin(i * 1.32) * 0.23)
    dummy.updateMatrix()
    ribosomes.setMatrixAt(i, dummy.matrix)
  }
  groups.er.add(ribosomes)

  // Mesh IDs also support direct raycasting, without relying on display names.
  for (const id of Object.keys(groups) as OrganelleId[]) groups[id].traverse(object => { object.userData.organelle = id })
  const select = (selected: OrganelleId) => {
    for (const id of Object.keys(groups) as OrganelleId[]) {
      groups[id].traverse(object => {
        if (object instanceof THREE.Mesh) {
          const materials = Array.isArray(object.material) ? object.material : [object.material]
          for (const material of materials) {
            if (material instanceof THREE.MeshStandardMaterial) {
              material.emissive.set(id === selected ? colors[id] : '#000000')
              material.emissiveIntensity = id === selected ? 0.13 : 0
            }
          }
        }
      })
    }
  }
  const setCut = (enabled: boolean, position: number) => {
    const z = 2.35 * (1 - Math.max(0, Math.min(1, position)))
    cutPlane.constant = z
    membrane.clippingPlanes = enabled ? [cutPlane] : []
    membrane.needsUpdate = true
    cutRim.visible = enabled
    const points: THREE.Vector3[] = []
    const r = Math.sqrt(1 - (z / 2.5) ** 2)
    for (let i = 0; i < 160; i += 1) {
      const a = i / 160 * Math.PI * 2
      const rough = 1 + 0.012 * Math.sin(a * 13) + 0.009 * Math.cos(a * 9)
      points.push(new THREE.Vector3(Math.cos(a) * 3.6 * r * rough, Math.sin(a) * 3 * r * rough, z))
    }
    cutRim.geometry.dispose()
    cutRim.geometry = new THREE.BufferGeometry().setFromPoints(points)
  }
  setCut(true, 0.65)
  return {
    root, groups, anchors, membrane, cutPlane, cutRim, select, setCut,
    dispose() {
      const geometries = new Set<THREE.BufferGeometry>()
      const materials = new Set<THREE.Material>()
      root.traverse(object => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
          geometries.add(object.geometry)
          for (const material of Array.isArray(object.material) ? object.material : [object.material]) materials.add(material)
        }
        if (object instanceof THREE.InstancedMesh) object.dispose()
      })
      geometries.forEach(geometry => geometry.dispose())
      materials.forEach(material => material.dispose())
      root.clear()
    },
  }
}
