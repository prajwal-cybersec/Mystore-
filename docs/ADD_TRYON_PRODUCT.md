# Adding a Try-On Enabled Product to MyStore

This guide explains how to add new products that support the live in-browser camera Try-On feature without modifying any frontend or tracking code. The feature is 100% data-driven.

---

## 1. Required Product Schema Fields

When creating or inserting a product row in PostgreSQL, populate these four fields:

| Field Name | Type | Description |
|---|---|---|
| `tryon_supported` | `BOOLEAN` | `true` to display the "Try On" button; `false` to hide it. |
| `tryon_type` | `TEXT` | One of: `tshirt`, `shirt`, `headphones`, `lipstick`, `blush`, `glasses`, `earrings`, `nose_pin`, `watch`. |
| `tryon_asset` | `TEXT` | Relative path to asset (e.g. `/public/tryon/<SKU>.png` or `/public/tryon/<SKU>.glb`). For makeup (lipstick/blush), set to `NULL`. |
| `tryon_config` | `JSONB` | Calibration parameters (scale, offsets, rotation, colors, etc.). |

---

## 2. Step-by-Step Workflow for New Products

### Step A: Place the Asset File
1. For **Apparel** (`tshirt`, `shirt`):
   - Prepare a clean, front-facing PNG with transparent background.
   - Save at: `backend/app/static/tryon/<SKU>.png` (accessible via `/public/tryon/<SKU>.png`).
2. For **3D Objects** (`glasses`, `earrings`, `headphones`, `watch`):
   - Prepare an optimized, Draco-compressed GLB file (< 1.5MB).
   - Save at: `backend/app/static/tryon/<SKU>.glb`.
3. For **Cosmetics** (`lipstick`, `blush`):
   - No file needed! Only color hex codes in `tryon_config`.

### Step B: Insert the Product into Database
Run an SQL INSERT statement or use your catalogue ingestion script:

```sql
INSERT INTO products (
    id, sku, name, brand, category, price_inr, image_url, description, attrs,
    tryon_supported, tryon_type, tryon_asset, tryon_config
) VALUES (
    gen_random_uuid(),
    'FAS-NEW-01',
    'Men Slim Fit Linen White Shirt',
    'LinenClub',
    'Fashion',
    1499.00,
    '/static/products/linen_white.jpg',
    '100% Pure Organic Linen Shirt',
    '{"color": "White", "sizes": ["M", "L", "XL"]}',
    true,
    'shirt',
    '/public/tryon/FAS-NEW-01.png',
    '{
        "scale": 1.0,
        "scaleX": 1.45,
        "scaleY": 1.35,
        "offsetX": 0.0,
        "offsetY": -0.04,
        "offsetZ": 0.0,
        "rotation": 0.0,
        "flip": false,
        "fadeAngleDeg": 60.0
    }'::jsonb
);
```

### Step C: Fine-Tune with Dev Calibration Mode
1. Open the store locally with calibration mode enabled:
   `http://localhost:8000/?calibrate=1`
2. Click **Try On** on your new product.
3. The real-time Dev Calibration overlay appears in the camera view:
   - Adjust **Scale**, **Offset X / Y / Z**, and **Rotation** sliders.
   - Toggle **Landmark Debug** to verify anchor alignment with Pose/Face landmarks.
4. Click **"Save to Product"**.
   - This calls `POST /api/tryon/calibrate/{product_id}` and persists calibration directly to the database.

---

## 3. Supported Try-On Types Reference

| Type | Tracking Engine | Default Anchors | Required Config Keys |
|---|---|---|---|
| `tshirt` | MediaPipe Pose | Shoulders (11, 12), Hips (23, 24) | `scale`, `scaleX`, `scaleY`, `offsetX`, `offsetY`, `fadeAngleDeg` |
| `shirt` | MediaPipe Pose | Shoulders (11, 12), Hips (23, 24) | `scale`, `scaleX`, `scaleY`, `offsetX`, `offsetY`, `fadeAngleDeg` |
| `lipstick` | MediaPipe FaceMesh | Lips (Outer/Inner polygon 61, 291, 0, 17) | `opacity`, `blendMode`, `gloss`, `defaultColor`, `colors` |
| `blush` | MediaPipe FaceMesh | Cheeks (Centers 116, 345) | `opacity`, `radiusMultiplier`, `defaultColor`, `colors` |
| `headphones` | MediaPipe FaceMesh | Ears (234, 454) & Head Top (10) | `scale`, `offsetX`, `offsetY`, `rotation` |
| `glasses` | MediaPipe FaceMesh | Eye Bridge (168, 6) & Inter-eye Distance | `scale`, `offsetX`, `offsetY`, `offsetZ`, `rotation` |
| `earrings` | MediaPipe FaceMesh | Earlobes (177, 401) | `scale`, `offsetX`, `offsetY`, `cutoffAngleDeg` |
| `watch` | MediaPipe Hands | Wrist (0) & Middle MCP (9) | `scale`, `offsetX`, `offsetY`, `offsetZ` |
