# Try-On 2D & 3D Asset Specification

This document specifies the exact technical requirements, coordinate systems, origins, and naming conventions for assets used by the MyStore real-time camera Try-On engine.

---

## 1. File Location & Naming Convention

All Try-On assets must be stored in:
- Filesystem path: `backend/app/static/tryon/<SKU>.<ext>`
- URL accessible at: `/public/tryon/<SKU>.<ext>` or `/static/tryon/<SKU>.<ext>`

Example:
- `backend/app/static/tryon/FAS-0002.png` -> `/public/tryon/FAS-0002.png`
- `backend/app/static/tryon/ELE-0002.png` -> `/public/tryon/ELE-0002.png`

---

## 2. 2D Apparel Cutouts (`tshirt`, `shirt`)

### Format & Dimensions
- **File Format**: `PNG` with 8-bit Alpha channel (transparency).
- **Resolution**: 800px to 1200px width, aspect ratio matching standard apparel garment (typically 3:4).
- **Max File Size**: 350 KB (use `pngquant` or lossless compression).
- **Background**: Completely transparent (Alpha = 0). No model head, neck, hands, or lower legs.

### Pose & Alignment
- **View**: Strict flat front view with arms slightly relaxed (not folded or crossed).
- **Anchor Center**: The center point between the left and right collar shoulders aligns with Pose landmarks 11 & 12.
- **Aspect Scaling**:
  - Width scales dynamically with shoulder distance: `width = distance(left_shoulder, right_shoulder) * scaleX`
  - Height scales dynamically with shoulder-to-hip length: `height = distance(mid_shoulder, mid_hip) * scaleY`
  - Perspective compensation: Compresses horizontally as the user turns left/right; fades out smoothly past 60° angle.

---

## 3. 3D Models (`glasses`, `earrings`, `headphones`, `watch`)

### Format & Compression
- **File Format**: `.glb` (Binary glTF 2.0).
- **Compression**: Draco mesh compression enabled.
- **Max File Size**: 1.5 MB maximum.
- **Materials**: Standard PBR (`MeshStandardMaterial` or `MeshPhysicalMaterial`).
- **Texture Maps**: Embedded BaseColor and Roughness/Metallic maps (Max 1024×1024px).

### 3D Coordinate System & Units
- **Three.js Standard Units**: 1 Unit = 1 Meter (or normalized face mesh units).
- **Orientation**:
  - `+Y` = Up (Crown of head)
  - `+X` = Right (User's left eye direction in mirrored camera)
  - `+Z` = Forward (Pointing toward camera)

| Try-On Type | Origin Point (0, 0, 0) | Default Rotation | Anchor Landmark |
|---|---|---|---|
| `glasses` | Center of bridge between lenses | Facing +Z, temples extending to -Z | Landmark 168 (Nasion / eye bridge) |
| `earrings` | Top of hook / stud post | Facing +Z, dangling toward -Y | Left earlobe (177) & Right earlobe (401) |
| `headphones` | Center of headband apex | Earcups along X-axis, facing +Z | Crown landmark 10 + ear anchors 234 & 454 |
| `watch` | Center of watch dial glass | Straps wrap along Y-axis, dial facing +Z | Wrist landmark 0 (HandLandmarker) |

---

## 4. Cosmetics & Makeup (`lipstick`, `blush`)

- **Asset Required**: None (Zero network download!).
- **Definition**: Defined purely as hex colors and opacity parameters inside `tryon_config`.
- **Lipstick Specs**:
  - Rendered dynamically via 2D SVG / Canvas path tracing the MediaPipe FaceMesh lips contour (indices 61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291).
  - Composite Mode: `multiply` with gloss highlight overlay.
- **Blush Specs**:
  - Rendered as soft radial Gaussian gradients centered on landmark 116 (left cheek) and 345 (right cheek).
  - Radius: Dynamic based on facial bounding box width.
