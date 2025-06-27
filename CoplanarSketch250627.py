import FreeCAD
import FreeCADGui
import Part
import Sketcher
import PartDesign
from PySide.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QPushButton, QTextEdit, QLabel, QInputDialog
from PySide.QtCore import Qt
import time

class EdgeDataCollector(QDockWidget):
    def __init__(self):
        super().__init__("CoplanarSketch")
        self.setWidget(self.create_ui())
        self.collected_edges = []
        self.edge_mass_center = FreeCAD.Vector(0, 0, 0)

    def create_ui(self):
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

        layout.addWidget(self.collect_button)
        layout.addWidget(self.select_coplanar_label)
        layout.addWidget(self.select_coplanar_button)
        layout.addWidget(self.create_sketch_button)
        layout.addWidget(self.info_display)
        widget.setLayout(layout)

        return widget

    def collect_data(self):
        self.info_display.clear()
        start_time = time.time()

        selection = FreeCADGui.Selection.getSelectionEx()
        if not selection:
            self.info_display.append("Error: No selection made.")
            return

        obj = selection[0].Object
        edges = obj.Shape.Edges
        self.collected_edges = [(edge, f"Edge{edges.index(edge)+1}") for edge in edges]

        all_points = [v.Point for edge, _ in self.collected_edges for v in edge.Vertexes]
        if all_points:
            self.edge_mass_center = sum(all_points, FreeCAD.Vector()).multiply(1.0 / len(all_points))

        duration = time.time() - start_time
        self.info_display.append(f"Collected {len(edges)} edges from {obj.Label}.")
        self.info_display.append(f"Elapsed time: {duration:.4f} seconds.\n")

    def select_coplanar_edges(self):
        start_time = time.time()
        selection = FreeCADGui.Selection.getSelectionEx()
        if not selection:
            self.info_display.append("Error: Select a face or two edges first.")
            return

        obj = selection[0].Object
        selected_edge_names = [name for s in selection for name in s.SubElementNames if name.startswith("Edge")]
        selected_face_names = [name for s in selection for name in s.SubElementNames if name.startswith("Face")]

        if selected_face_names:
            face_idx = int(selected_face_names[0][4:]) - 1
            plane_normal = obj.Shape.Faces[face_idx].Surface.Axis
            plane_point = obj.Shape.Faces[face_idx].CenterOfMass
        elif len(selected_edge_names) >= 2:
            edges = obj.Shape.Edges
            selected_edges = [edges[int(name[4:]) - 1] for name in selected_edge_names]
            v1, v2 = [v.Point for v in selected_edges[0].Vertexes]
            v3_candidates = [v.Point for v in selected_edges[1].Vertexes if v.Point != v1 and v.Point != v2]

            if not v3_candidates:
                self.info_display.append("Error: Could not define a valid plane from selected edges.")
                return

            v3 = v3_candidates[0]
            plane_normal = (v2 - v1).cross(v3 - v1)
            if plane_normal.Length < 1e-6:
                self.info_display.append("Error: Edges are colinear; cannot define plane.")
                return

            plane_point = v1
        else:
            self.info_display.append("Error: Select either a face or two edges.")
            return

        def is_coplanar(edge):
            v1, v2 = [v.Point for v in edge.Vertexes]
            return abs((v1 - plane_point).dot(plane_normal)) < 0.001 and abs((v2 - plane_point).dot(plane_normal)) < 0.001

        coplanar_edges = [e for e in obj.Shape.Edges if is_coplanar(e)]

        FreeCADGui.Selection.clearSelection()
        for edge in coplanar_edges:
            name = [n for e, n in self.collected_edges if e.isSame(edge)]
            if name:
                FreeCADGui.Selection.addSelection(obj, name[0])

        duration = time.time() - start_time
        self.info_display.append(f"Selected {len(coplanar_edges)} coplanar edges.")
        self.info_display.append(f"Elapsed time: {duration:.4f} seconds.\n")

    def calculate_robust_plane_normal_and_placement(self, vertices, source_object=None):
        if len(vertices) < 3:
            return FreeCAD.Vector(0, 0, 1), FreeCAD.Vector(0, 0, 0)

        center = sum(vertices, FreeCAD.Vector()).multiply(1.0 / len(vertices))
        vectors = [v.sub(center) for v in vertices]

        best_normal = None
        best_magnitude = 0
        for i in range(len(vectors)):
            for j in range(i+1, len(vectors)):
                for k in range(j+1, len(vectors)):
                    n = (vectors[j] - vectors[i]).cross(vectors[k] - vectors[i])
                    if n.Length > best_magnitude:
                        best_magnitude = n.Length
                        best_normal = n.normalize()

        if not best_normal:
            best_normal = FreeCAD.Vector(0, 0, 1)

        if self.edge_mass_center:
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
            self.info_display.append("Error: No active FreeCAD document.")
            return

        start_time = time.time()
        doc.openTransaction("Create Outward-Facing Sketch")
        try:
            selected_edges = []
            selected_objects = FreeCADGui.Selection.getSelectionEx()
            source_object = None

            for sel in selected_objects:
                source_object = sel.Object if not source_object else source_object
                selected_edges.extend([sub for sub in sel.SubObjects if isinstance(sub, Part.Edge)])

            if not selected_edges:
                self.info_display.append("No edges selected.")
                doc.abortTransaction()
                return

            all_vertices = [v.Point for edge in selected_edges for v in edge.Vertexes]
            unique_vertices = []
            for p in all_vertices:
                if not any((p - q).Length < 1e-4 for q in unique_vertices):
                    unique_vertices.append(p)

            normal, center = self.calculate_robust_plane_normal_and_placement(unique_vertices, source_object)
            placement = self.create_robust_placement(normal, center)

            temp_sketch = doc.addObject("Sketcher::SketchObject", "TempSketch")
            temp_sketch.Placement = placement
            doc.recompute()

            final_sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
            final_sketch.Placement = placement
            doc.removeObject(temp_sketch.Name)

            edge_map = {}
            tolerance = 0.001
            for edge in selected_edges:
                v_start, v_end = edge.Vertexes[0].Point, edge.Vertexes[-1].Point
                if (v_start - v_end).Length < tolerance:
                    continue  # Skip degenerate

                v_start_local = final_sketch.getGlobalPlacement().inverse().multVec(v_start)
                v_end_local = final_sketch.getGlobalPlacement().inverse().multVec(v_end)

                geo_index = final_sketch.addGeometry(Part.LineSegment(v_start_local, v_end_local), False)
                final_sketch.setConstruction(geo_index, True)

                for point, vid in [(v_start, 1), (v_end, 2)]:
                    key = (round(point.x, 5), round(point.y, 5), round(point.z, 5))
                    edge_map.setdefault(key, []).append((geo_index, vid))

            for group in edge_map.values():
                base = group[0]
                for other in group[1:]:
                    try:
                        final_sketch.addConstraint(Sketcher.Constraint('Coincident', base[0], base[1], other[0], other[1]))
                    except Exception as e:
                        FreeCAD.Console.PrintWarning(f"Coincident error: {e}\n")

            doc.recompute()
            FreeCADGui.Selection.clearSelection()
            FreeCADGui.Selection.addSelection(final_sketch)
            FreeCADGui.activeDocument().activeView().viewAxonometric()
            FreeCADGui.activeDocument().activeView().fitAll()

            duration = time.time() - start_time
            self.info_display.append("Sketch created with outward-facing normal and coincident construction geometry.")
            self.info_display.append(f"Elapsed time: {duration:.4f} seconds.\n")
            doc.commitTransaction()

        except Exception as e:
            doc.abortTransaction()
            self.info_display.append(f"Sketch creation failed:\n{e}")
            FreeCAD.Console.PrintError(f"Sketch error: {e}\n")

def show_edge_data_collector_docker():
    mw = FreeCADGui.getMainWindow()
    for d in mw.findChildren(QDockWidget):
        if d.windowTitle() == "CoplanarSketch":
            d.close()
            d.deleteLater()
    mw.addDockWidget(Qt.RightDockWidgetArea, EdgeDataCollector())

show_edge_data_collector_docker()
