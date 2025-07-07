import FreeCAD
import FreeCADGui
import Part
import Sketcher
import PartDesign
from PySide.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QPushButton, QTextEdit, QLabel, QMessageBox, QInputDialog, QApplication
from PySide.QtCore import Qt
import time

def is_close(p1, p2, tol=1e-4):
    return (p1 - p2).Length < tol

class EdgeDataCollector(QDockWidget):
    def __init__(self):
        super().__init__("CoplanarSketch")
        self.setWidget(self.build_ui())
        self.collected_edges = []
        self.edge_mass_center = FreeCAD.Vector(0, 0, 0)

    def build_ui(self):
        widget = QWidget()
        layout = QVBoxLayout()

        self.collect_button = QPushButton("Collect Edge Data")
        self.collect_button.clicked.connect(self.collect_data)

        self.select_coplanar_label = QLabel("Select a face or two coplanar edges before using this button.")
        self.select_coplanar_button = QPushButton("Select Coplanar Edges")
        self.select_coplanar_button.clicked.connect(self.select_coplanar_edges)

        self.create_sketch_button = QPushButton("Create Sketch from Selection")
        self.create_sketch_button.clicked.connect(self.create_sketch_from_selection)

        self.info_display = QTextEdit()
        self.info_display.setReadOnly(True)

        for widget_item in [
            self.collect_button, self.select_coplanar_label,
            self.select_coplanar_button, self.create_sketch_button, self.info_display
        ]:
            layout.addWidget(widget_item)

        widget.setLayout(layout)
        return widget

    def collect_data(self):
        self.info_display.clear()
        start_time = time.time()
        selection = FreeCADGui.Selection.getSelectionEx()

        if not selection:
            self.info_display.append("[Error] No selection made.")
            return

        obj = selection[0].Object
        edges = obj.Shape.Edges
        self.collected_edges = [(edge, f"Edge{edges.index(edge) + 1}") for edge in edges]

        all_points = [v.Point for edge, _ in self.collected_edges for v in edge.Vertexes]
        if all_points:
            self.edge_mass_center = sum(all_points, FreeCAD.Vector()).multiply(1.0 / len(all_points))

        duration = time.time() - start_time
        self.info_display.append(f"[Info] Collected {len(edges)} edges from {obj.Label}.")
        self.info_display.append(f"[Timing] Elapsed time: {duration:.4f} seconds.\n")

    def select_coplanar_edges(self):
        start_time = time.time()
        selection = FreeCADGui.Selection.getSelectionEx()
        if not selection:
            self.info_display.append("[Error] Select a face or two edges first.")
            return

        obj = selection[0].Object
        edge_names = [n for s in selection for n in s.SubElementNames if n.startswith("Edge")]
        face_names = [n for s in selection for n in s.SubElementNames if n.startswith("Face")]

        if face_names:
            face_idx = int(face_names[0][4:]) - 1
            face = obj.Shape.Faces[face_idx]
            plane_normal = face.Surface.Axis
            plane_point = face.CenterOfMass
        elif len(edge_names) >= 2:
            edges = obj.Shape.Edges
            selected_edges = [edges[int(n[4:]) - 1] for n in edge_names]
            v1, v2 = [v.Point for v in selected_edges[0].Vertexes]
            v3_candidates = [v.Point for v in selected_edges[1].Vertexes if not is_close(v.Point, v1) and not is_close(v.Point, v2)]
            if not v3_candidates:
                self.info_display.append("[Error] Could not define a valid plane from selected edges.")
                return
            v3 = v3_candidates[0]
            plane_normal = (v2 - v1).cross(v3 - v1)
            if plane_normal.Length < 1e-6:
                self.info_display.append("[Error] Edges are colinear; cannot define plane.")
                return
            plane_point = v1
        else:
            self.info_display.append("[Error] Select either a face or two edges.")
            return

        def is_coplanar(edge):
            v1, v2 = [v.Point for v in edge.Vertexes]
            return all(abs((pt - plane_point).dot(plane_normal)) < 0.001 for pt in [v1, v2])

        coplanar_edges = [edge for edge in obj.Shape.Edges if is_coplanar(edge)]

        FreeCADGui.Selection.clearSelection()
        for edge in coplanar_edges:
            name = [n for e, n in self.collected_edges if e.isSame(edge)]
            if name:
                FreeCADGui.Selection.addSelection(obj, name[0])

        duration = time.time() - start_time
        self.info_display.append(f"[Step] Selected {len(coplanar_edges)} coplanar edges.")
        self.info_display.append(f"[Timing] Elapsed time: {duration:.4f} seconds.\n")

    def calculate_robust_plane_normal_and_placement(self, vertices, source_object=None):
        if len(vertices) < 3:
            return FreeCAD.Vector(0, 0, 1), FreeCAD.Vector(0, 0, 0)

        center = sum(vertices, FreeCAD.Vector()).multiply(1.0 / len(vertices))
        vectors = [v.sub(center) for v in vertices]

        best_normal = None
        best_magnitude = 0
        for i in range(len(vectors)):
            for j in range(i + 1, len(vectors)):
                for k in range(j + 1, len(vectors)):
                    n = (vectors[j] - vectors[i]).cross(vectors[k] - vectors[i])
                    if n.Length > best_magnitude:
                        best_magnitude = n.Length
                        best_normal = n.normalize()

        best_normal = best_normal or FreeCAD.Vector(0, 0, 1)

        delta = center.sub(self.edge_mass_center)
        if delta.Length > 1e-6 and delta.normalize().dot(best_normal) < 0:
            best_normal = best_normal.multiply(-1)

        return best_normal, center

    def create_robust_placement(self, normal, center):
        normal = normal.normalize() if normal.Length > 1e-6 else FreeCAD.Vector(0, 0, 1)
        z_axis = FreeCAD.Vector(0, 0, 1)
        if abs(normal.dot(z_axis)) > 0.999:
            rotation = FreeCAD.Rotation() if normal.z > 0 else FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 180)
        else:
            rotation = FreeCAD.Rotation(z_axis, normal)
        return FreeCAD.Placement(center, rotation)

    def create_sketch_from_selection(self):
        doc = FreeCAD.ActiveDocument
        if not doc:
            self.info_display.append("[Error] No active FreeCAD document.")
            return

        start_time = time.time()
        doc.openTransaction("Create Sketch with Construction Geometry")

        temp_sketch = final_sketch = target_body = None
        sketch_created = False

        try:
            edges = []
            selection = FreeCADGui.Selection.getSelectionEx()
            source_object = None

            for sel in selection:
                source_object = source_object or sel.Object
                edges.extend([o for o in sel.SubObjects if isinstance(o, Part.Edge)])

            if not edges:
                self.info_display.append("[Error] No edges selected.")
                doc.abortTransaction()
                return

            all_vertices = [v.Point for e in edges for v in e.Vertexes]
            unique_vertices = []
            for p in all_vertices:
                if all(not is_close(p, q) for q in unique_vertices):
                    unique_vertices.append(p)

            normal, center = self.calculate_robust_plane_normal_and_placement(unique_vertices, source_object)
            placement = self.create_robust_placement(normal, center)

            temp_sketch = doc.addObject("Sketcher::SketchObject", "TempSketch")
            temp_sketch.Placement = placement
            doc.recompute()

            body_names = [o.Name for o in doc.Objects if o.isDerivedFrom("PartDesign::Body")]
            options = ["<Standalone (Part Workbench)>", "<Create New Body (PartDesign)>"] + body_names
            item, ok = QInputDialog.getItem(FreeCADGui.getMainWindow(),
                                            "Sketch Placement Options",
                                            "Choose a placement option:",
                                            options, 0, False)

            if not ok or not item:
                self.info_display.append("[Info] Sketch creation cancelled by user.")
                if temp_sketch:
                    doc.removeObject(temp_sketch.Name)
                doc.abortTransaction()
                return

            if item == "<Standalone (Part Workbench)>":
                final_sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
                final_sketch.Placement = temp_sketch.Placement
            else:
                target_body = doc.addObject("PartDesign::Body", "NewBody") if item == "<Create New Body (PartDesign)>" else doc.getObject(item)
                final_sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
                target_body.ViewObject.dropObject(final_sketch, None, '', [])
                doc.recompute()

                final_sketch.AttachmentSupport = [(target_body.Origin.OriginFeatures[0], '')]
                final_sketch.MapMode = 'ObjectXY'
                final_sketch.AttachmentOffset.Base = temp_sketch.Placement.Base
                final_sketch.AttachmentOffset.Rotation = temp_sketch.Placement.Rotation
                final_sketch.Placement = FreeCAD.Placement()

            doc.recompute()

            block_constraints = []
            vertex_map = {}
            tolerance = 0.001

            for edge in edges:
                start_global = edge.Vertexes[0].Point
                end_global = edge.Vertexes[-1].Point

                if is_close(start_global, end_global, tolerance):
                    FreeCAD.Console.PrintWarning(f"[Warning] Skipped degenerate edge at {start_global}.\n")
                    continue

                start_local = final_sketch.getGlobalPlacement().inverse().multVec(start_global)
                end_local = final_sketch.getGlobalPlacement().inverse().multVec(end_global)

                geo_index = final_sketch.addGeometry(Part.LineSegment(start_local, end_local), False)
                final_sketch.setConstruction(geo_index, True)

                for pt, vertex_id in [(start_global, 1), (end_global, 2)]:
                    pt_key = (pt.x, pt.y, pt.z)
                    found_key = next((k for k in vertex_map if is_close(pt, FreeCAD.Vector(*k), tolerance)), None)
                    if found_key:
                        vertex_map[found_key].append((geo_index, vertex_id))
                    else:
                        vertex_map[pt_key] = [(geo_index, vertex_id)]

                constraint_idx = final_sketch.addConstraint(Sketcher.Constraint('Block', geo_index))
                block_constraints.append(constraint_idx)

            coincident_added = 0
            for pt_key, refs in vertex_map.items():
                if len(refs) > 1:
                    first_geo, first_id = refs[0]
                    for next_geo, next_id in refs[1:]:
                        try:
                            final_sketch.addConstraint(Sketcher.Constraint('Coincident', first_geo, first_id, next_geo, next_id))
                            coincident_added += 1
                        except Exception as e:
                            FreeCAD.Console.PrintWarning(f"[Warning] Failed to add coincident constraint for {pt_key}: {e}\n")

            for idx in block_constraints:
                try:
                    final_sketch.setVirtualSpace(idx, True)
                except Exception as e:
                    self.info_display.append(f"[Warning] Constraint index {idx} visibility could not be set: {e}")
                    FreeCAD.Console.PrintWarning(f"[Warning] Virtual space set failed for constraint {idx}: {e}\n")

            sketch_created = True
            doc.commitTransaction()

        except Exception as e:
            self.info_display.append(f"[Error] Sketch creation failed:\n\n{e}")
            FreeCAD.Console.PrintError(f"[Error] Macro exception: {e}\n")
            doc.abortTransaction()

        finally:
            if temp_sketch and hasattr(temp_sketch, 'Name'):
                try:
                    doc.removeObject(temp_sketch.Name)
                    doc.recompute()
                except Exception as e:
                    FreeCAD.Console.PrintWarning(f"[Warning] Could not remove temporary sketch: {e}\n")

            if sketch_created and final_sketch:
                FreeCADGui.Selection.clearSelection()
                FreeCADGui.Selection.addSelection(final_sketch)
                FreeCADGui.activeDocument().activeView().viewAxonometric()
                FreeCADGui.activeDocument().activeView().fitAll()

                duration = time.time() - start_time
                self.info_display.append(f"[Success] Sketch created with transformed geometry.")
                self.info_display.append(f"[Info] Added {coincident_added} coincident constraints.")
            else:
                self.info_display.append("[Error] Sketch creation incomplete or cancelled.")

def show_edge_data_collector_docker():
    # Close existing dockers with the same name (clean-up behavior preserved)
    mw = FreeCADGui.getMainWindow()
    for d in mw.findChildren(QDockWidget):
        if d.windowTitle() == "CoplanarSketch":
            d.close()
            d.deleteLater()

    # Raise existing instance if available
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, EdgeDataCollector):
            widget.raise_()
            widget.activateWindow()
            return

    # Launch new instance
    docker = EdgeDataCollector()
    FreeCADGui.getMainWindow().addDockWidget(Qt.RightDockWidgetArea, docker)

show_edge_data_collector_docker()
