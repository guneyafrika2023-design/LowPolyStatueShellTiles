import adsk.core, adsk.fusion, traceback, math, os

# ── Configuration ──────────────────────────────────────────────────
SHELL_THICKNESS_MM = 3.0
EPSILON_PERCENT    = 8.0
MAX_PAIRS          = None       # Set to None to process all pairs
TEXT_HEIGHT_CM     = 0.3
# ───────────────────────────────────────────────────────────────────

def distance(p1, p2):
    dx = p1.x - p2.x
    dy = p1.y - p2.y
    dz = p1.z - p2.z
    return math.sqrt(dx*dx + dy*dy + dz*dz)

def draw_polygon_in_sketch(sketch, face):
    """Draw all edges of a face into a sketch by converting
    each vertex from model space to sketch space.
    Works for triangles, quads, or any n-gon."""
    lines = sketch.sketchCurves.sketchLines
    verts = [v.geometry for v in face.vertices]
    pts   = [sketch.modelToSketchSpace(v) for v in verts]
    p     = [adsk.core.Point3D.create(pt.x, pt.y, 0) for pt in pts]
    n     = len(p)
    for i in range(n):
        lines.addByTwoPoints(p[i], p[(i + 1) % n])

def draw_polygon_mirrored(sketch, face):
    """Draw all edges of a face into a sketch with X coordinates
    negated — for DXF export only, does not affect the 3D model."""
    lines = sketch.sketchCurves.sketchLines
    verts = [v.geometry for v in face.vertices]
    pts   = [sketch.modelToSketchSpace(v) for v in verts]
    p     = [adsk.core.Point3D.create(-pt.x, pt.y, 0) for pt in pts]
    n     = len(p)
    for i in range(n):
        lines.addByTwoPoints(p[i], p[(i + 1) % n])

def add_text_to_sketch(sketch, label, sketch_pt, height_cm):
    """Add a text label at the given sketch space point
    using setAsAlongPath to avoid the bounding box rectangle."""

    line_start = adsk.core.Point3D.create(
        sketch_pt.x,
        sketch_pt.y,
        0
    )
    line_end = adsk.core.Point3D.create(
        sketch_pt.x + height_cm * len(label) * 0.6,
        sketch_pt.y,
        0
    )
    path_line = sketch.sketchCurves.sketchLines.addByTwoPoints(
        line_start, line_end
    )
    path_line.isConstruction = True

    texts      = sketch.sketchTexts
    expression = f"'{label}'"
    height     = adsk.core.ValueInput.createByReal(height_cm)
    text_input = texts.createInput3(expression, height)
    text_input.setAsAlongPath(
        path_line,
        True,
        adsk.core.HorizontalAlignments.LeftHorizontalAlignment,
        0
    )
    return texts.add(text_input)

def run(_context):
    app = adsk.core.Application.get()
    ui  = app.userInterface

    try:
        print('Script started.')

        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox('ERROR: No active Fusion design found.')
            return

        root = design.rootComponent
        body = root.bRepBodies.item(0)
        if not body:
            ui.messageBox('ERROR: No body found in root component.')
            return

        print(f'Body: {body.name}, faces: {body.faces.count}')

        # ── Step 1: Build the two face sets via shell.isVoid ───────
        Set_External_Faces = []
        Set_Internal_Faces = []

        for lump_idx in range(body.lumps.count):
            lump = body.lumps.item(lump_idx)
            for shell_idx in range(lump.shells.count):
                shell = lump.shells.item(shell_idx)
                for face_idx in range(shell.faces.count):
                    face = shell.faces.item(face_idx)
                    if shell.isVoid:
                        Set_Internal_Faces.append(face)
                    else:
                        Set_External_Faces.append(face)

        print(f'External: {len(Set_External_Faces)}, Internal: {len(Set_Internal_Faces)}')

        # ── Step 2: Match pairs by centroid distance ───────────────
        thickness_cm = SHELL_THICKNESS_MM / 10.0
        epsilon_cm   = thickness_cm * (EPSILON_PERCENT / 100.0)
        dist_min     = thickness_cm - epsilon_cm
        dist_max     = thickness_cm + epsilon_cm

        matched_pairs = []
        used_internal = set()

        for ext_face in Set_External_Faces:
            ext_c     = ext_face.centroid
            best_face = None
            best_dist = None
            for int_face in Set_Internal_Faces:
                if id(int_face) in used_internal:
                    continue
                d = distance(ext_c, int_face.centroid)
                if dist_min <= d <= dist_max:
                    if best_dist is None or d < best_dist:
                        best_face = int_face
                        best_dist = d
            if best_face is not None:
                matched_pairs.append((ext_face, best_face))
                used_internal.add(id(best_face))

        print(f'Matched pairs: {len(matched_pairs)}')

        limit = len(matched_pairs) if MAX_PAIRS is None else min(MAX_PAIRS, len(matched_pairs))
        ui.messageBox(
            f'Matched {len(matched_pairs)} pairs.\n'
            f'Processing {limit} pair(s).\n'
        )

        # ── Step 3: Ask user where to save DXF files ───────────────
        folderDlg = ui.createFolderDialog()
        folderDlg.title = 'Select output folder for DXF files'
        if folderDlg.showDialog() != adsk.core.DialogResults.DialogOK:
            return
        OUTPUT_FOLDER = folderDlg.folder

        export_mgr = design.exportManager
        created    = 0
        errors     = []

        for pair_idx, (ext_face, int_face) in enumerate(matched_pairs[:limit]):
            try:
                print(f'Pair {pair_idx}: building construction plane...')

                # ── Construction plane from external triangle verts ─
                verts = [v for v in ext_face.vertices]
                plane_input = root.constructionPlanes.createInput()
                ok = plane_input.setByThreePoints(
                    verts[0], verts[1], verts[2]
                )
                if not ok:
                    errors.append(f'Pair {pair_idx}: setByThreePoints failed.')
                    continue
                plane = root.constructionPlanes.add(plane_input)

                # ── Create permanent sketch on that plane ──────────
                # This sketch sits correctly on the 3D model
                sketch = root.sketches.add(plane)
                sketch.name = f'Pair_{pair_idx:03d}'
                draw_polygon_in_sketch(sketch, ext_face)
                draw_polygon_in_sketch(sketch, int_face)

                # Add text at normal (unmirrored) centroid position
                ext_c     = ext_face.centroid
                sketch_pt = sketch.modelToSketchSpace(ext_c)
                add_text_to_sketch(
                    sketch,
                    f'{pair_idx:03d}',
                    sketch_pt,
                    TEXT_HEIGHT_CM
                )
                print(f'Pair {pair_idx}: permanent sketch created OK.')

                # ── Create temporary mirrored sketch for DXF only ──
                # Same plane, mirrored X coordinates, deleted after export
                temp_sketch = root.sketches.add(plane)
                temp_sketch.name = f'Pair_{pair_idx:03d}_DXF_TEMP'
                draw_polygon_mirrored(temp_sketch, ext_face)
                draw_polygon_mirrored(temp_sketch, int_face)

                # Text at mirrored centroid position (X negated)
                # but text characters are not flipped
                mirrored_pt = adsk.core.Point3D.create(
                    -sketch_pt.x,
                    sketch_pt.y,
                    0
                )
                add_text_to_sketch(
                    temp_sketch,
                    f'{pair_idx:03d}',
                    mirrored_pt,
                    TEXT_HEIGHT_CM
                )
                print(f'Pair {pair_idx}: temporary mirrored sketch created.')

                # ── Export temp sketch as DXF ──────────────────────
                dxf_path = os.path.join(OUTPUT_FOLDER, f'Pair_{pair_idx:03d}.dxf')
                dxf_options = export_mgr.createDXFSketchExportOptions(
                    dxf_path, temp_sketch
                )
                export_mgr.execute(dxf_options)
                print(f'Pair {pair_idx}: DXF saved to {dxf_path}')

                # ── Delete the temporary sketch ────────────────────
                temp_sketch.deleteMe()
                print(f'Pair {pair_idx}: temporary sketch deleted.')

                created += 1

            except Exception as e:
                errors.append(f'Pair {pair_idx}: {str(e)}')
                print(f'Pair {pair_idx}: ERROR - {str(e)}')
                continue

        app.activeViewport.fit()

        summary = [
            f'Sketches created and exported : {created}',
            f'Errors                        : {len(errors)}',
            f'DXF files saved to: {OUTPUT_FOLDER}',
        ]
        if errors:
            summary.append('')
            summary.append('Error details:')
            summary.extend(f'  {e}' for e in errors)

        ui.messageBox('\n'.join(summary))

    except:
        ui.messageBox('EXCEPTION:\n\n' + traceback.format_exc())
