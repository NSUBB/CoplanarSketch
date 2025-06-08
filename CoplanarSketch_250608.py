import FreeCAD
import FreeCADGui
import Part
import Sketcher
import PartDesign
from PySide.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QPushButton, QTextEdit, QLabel, QMessageBox, QInputDialog, QApplication
from PySide.QtCore import Qt, QTimer
import PySide.QtGui as QtGui
import PySide.QtCore as QtCore
import time

class EdgeDataCollector(QDockWidget):
    def __init__(self):
        super().__init__("CoplanarSketch")
        self.setWidget(self.create_ui())
        self.collected_edges = []
        # Removed self.progress_dialog as it's being removed

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

    # Removed _close_progress_dialog method as QProgressDialog is being removed

    def collect_data(self):
        start_time = time.time()
        selection = FreeCADGui.Selection.getSelectionEx()

        if not selection:
            self.info_display.setText("Error: No selection made.")
            return

        obj = selection[0].Object
        edges = obj.Shape.Edges

        self.collected_edges = [(edge, f"Edge{edges.index(edge) + 1}") for edge in edges]

        edge_data = [f"{name}: {edge.Vertexes[0].Point} -> {edge.Vertexes[1].Point}" for edge, name in self.collected_edges[:10]]

        duration = time.time() - start_time

        output = f"Collected {len(edges)} edges.\nProcess completed in {duration:.4f} seconds.\n"
        output += "\n".join(edge_data)
        self.info_display.setText(output)

    def select_coplanar_edges(self):
        selection = FreeCADGui.Selection.getSelectionEx()
        if not selection:
            self.info_display.setText("Error: Select a face or two edges first.")
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

            v1, v2 = [vertex.Point for vertex in selected_edges[0].Vertexes]
            v3_candidates = [vertex.Point for vertex in selected_edges[1].Vertexes if vertex.Point != v1 and vertex.Point != v2]

            if not v3_candidates:
                self.info_display.setText("Error: Could not find a valid third point for plane definition.")
                return

            v3 = v3_candidates[0]
            plane_normal = (v2 - v1).cross(v3 - v1)
            if plane_normal.Length < 0.0001:
                self.info_display.setText("Error: Selected edges share a vertex in a way that prevents proper plane calculation.")
                return

            plane_point = v1
        else:
            self.info_display.setText("Error: Need at least a face or two edges for coplanar detection.")
            return

        def is_coplanar(edge):
            v1, v2 = [vertex.Point for vertex in edge.Vertexes]
            def point_on_plane(point):
                return abs((point - plane_point).dot(plane_normal)) < 0.001
            return point_on_plane(v1) and point_on_plane(v2)

        coplanar_edges = [edge for edge in obj.Shape.Edges if is_coplanar(edge)]

        FreeCADGui.Selection.clearSelection()
        for edge in coplanar_edges:
            edge_name = [name for e, name in self.collected_edges if e.isSame(edge)]
            if edge_name:
                FreeCADGui.Selection.addSelection(obj, edge_name[0])

        self.info_display.setText(f"Selected {len(coplanar_edges)} coplanar edges.")

    def calculate_plane_normal(self, vertices):
        """Calculate a normal from three non-collinear points."""
        if len(vertices) < 3:
            return FreeCAD.Vector(0, 0, 1)

        for i in range(len(vertices) - 2):
            p1, p2, p3 = vertices[i], vertices[i+1], vertices[i+2]
            v1 = p2.sub(p1)
            v2 = p3.sub(p1)

            if v1.Length == 0 or v2.Length == 0:
                continue

            normal = v1.cross(v2).normalize()
            if normal.Length > 0:
                return normal

        return FreeCAD.Vector(0, 0, 1)

    def calculate_midpoint(self, vertices):
        """Find the center of all selected vertices."""
        if not vertices:
            return FreeCAD.Vector(0,0,0) # Return origin if no vertices
        x_avg = sum(v.x for v in vertices) / len(vertices)
        y_avg = sum(v.y for v in vertices) / len(vertices)
        z_avg = sum(v.z for v in vertices) / len(vertices)

        return FreeCAD.Vector(x_avg, y_avg, z_avg)

    def create_sketch_from_selection(self):
        """Create a sketch with correctly transformed 3D construction geometry from selected edges."""
        doc = FreeCAD.ActiveDocument
        if not doc:
            self.info_display.setText("Error: No active FreeCAD document. Please open a document.")
            return

        doc.openTransaction("Create Sketch with Construction Geometry") 
        
        temp_sketch = None
        final_sketch = None
        target_body = None
        sketch_created_successfully = False

        try:
            edges = []
            selected_objects = FreeCADGui.Selection.getSelectionEx()

            for obj_ex in selected_objects:
                edges.extend([subobj for subobj in obj_ex.SubObjects if isinstance(subobj, Part.Edge)])

            if not edges:
                self.info_display.setText("No edges selected for sketch creation.")
                doc.abortTransaction() 
                return

            vertices_global = [edge.Vertexes[0].Point for edge in edges]
            vertices_global += [edge.Vertexes[-1].Point for edge in edges]

            plane_normal = self.calculate_plane_normal(vertices_global)
            midpoint = self.calculate_midpoint(vertices_global)
            
            # Create a temporary standalone sketch to determine the global placement
            temp_sketch = doc.addObject("Sketcher::SketchObject", "TempSketch")
            temp_sketch.Placement = FreeCAD.Placement(midpoint, FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), plane_normal))
            doc.recompute() 

            # Prepare options for the dropdown
            body_names = [obj.Name for obj in doc.Objects if obj.isDerivedFrom("PartDesign::Body")]
            body_selection_options = ["<Standalone (Part Workbench)>", "<Create New Body (PartDesign)>"] + body_names

            item, ok = QInputDialog.getItem(FreeCADGui.getMainWindow(),
                                           "Sketch Placement Options",
                                           "Choose a placement option:",
                                           body_selection_options, 0, False)
            
            if not ok or not item:
                self.info_display.setText("Sketch creation cancelled by user.")
                if temp_sketch and hasattr(temp_sketch, 'Name'): # Robust check for temp_sketch
                    doc.removeObject(temp_sketch.Name)
                doc.abortTransaction() 
                return

            if item == "<Standalone (Part Workbench)>":
                final_sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
                final_sketch.Placement = temp_sketch.Placement 
                FreeCAD.Console.PrintMessage("Sketch created as Standalone in document root.\n") 

            elif item == "<Create New Body (PartDesign)>":
                # Create a new body directly, let FreeCAD handle unique naming
                target_body = doc.addObject("PartDesign::Body", "NewBody") 
                target_body.Label = "Body" # Set a user-friendly label

                final_sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
                # Drop into the newly created body
                target_body.ViewObject.dropObject(final_sketch, None, '', [])
                doc.recompute() # Recompute after dropping to ensure sketch is in body tree

                final_sketch.AttachmentSupport = [(target_body.Origin.OriginFeatures[0], '')]
                final_sketch.MapMode = 'ObjectXY'
                # Directly copy Placement's components to AttachmentOffset
                final_sketch.AttachmentOffset.Base = temp_sketch.Placement.Base
                final_sketch.AttachmentOffset.Rotation = temp_sketch.Placement.Rotation
                final_sketch.Placement = App.Placement() # Reset sketch's placement to identity as it's now attached
                FreeCAD.Console.PrintMessage("Created new PartDesign Body and attached sketch to its XY_Plane.\n") 

            else: # User selected an existing body
                target_body = doc.getObject(item)
                if target_body:
                    final_sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
                    # Drop into the selected existing body
                    target_body.ViewObject.dropObject(final_sketch, None, '', [])
                    doc.recompute() # Recompute after dropping to ensure sketch is in body tree

                    final_sketch.AttachmentSupport = [(target_body.Origin.OriginFeatures[0], '')]
                    final_sketch.MapMode = 'ObjectXY'
                    # Directly copy Placement's components to AttachmentOffset
                    final_sketch.AttachmentOffset.Base = temp_sketch.Placement.Base
                    final_sketch.AttachmentOffset.Rotation = temp_sketch.Placement.Rotation
                    final_sketch.Placement = App.Placement() # Reset sketch's placement to identity as it's now attached
                    FreeCAD.Console.PrintMessage(f"Attached sketch to existing PartDesign Body '{target_body.Name}'s XY_Plane.\n") 
                else:
                    self.info_display.setText(f"Error: Invalid Body '{item}' selected. Creating sketch Standalone.")
                    final_sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
                    final_sketch.Placement = temp_sketch.Placement 
                    FreeCAD.Console.PrintMessage("Invalid Body selected, sketch created as Standalone.\n") 
            
            doc.recompute() 

            block_constraint_indices = []
            vertex_map = {} 
            tolerance = 0.001 

            for edge in edges:
                start_global = edge.Vertexes[0].Point
                end_global = edge.Vertexes[-1].Point
                
                if (start_global - end_global).Length < tolerance:
                    FreeCAD.Console.PrintWarning(f"Skipping degenerate edge at {start_global} as start and end points are identical (length < {tolerance}).\n") 
                    continue 
                
                # Transform global points to final_sketch's local coordinate system
                start_local = final_sketch.getGlobalPlacement().inverse().multVec(start_global)
                end_local = final_sketch.getGlobalPlacement().inverse().multVec(end_global)
                
                geo_index = final_sketch.addGeometry(Part.LineSegment(start_local, end_local), False)
                final_sketch.setConstruction(geo_index, True)
                
                start_global_tuple = (start_global.x, start_global.y, start_global.z)
                end_global_tuple = (end_global.x, end_global.y, end_global.z)
                
                found_start_key = None
                for key_tuple in vertex_map:
                    existing_point_vec = FreeCAD.Vector(key_tuple[0], key_tuple[1], key_tuple[2])
                    if (start_global - existing_point_vec).Length < tolerance:
                        found_start_key = key_tuple
                        break
                if found_start_key:
                    vertex_map[found_start_key].append((geo_index, 1))
                else:
                    vertex_map[start_global_tuple] = [(geo_index, 1)]

                found_end_key = None
                for key_tuple in vertex_map:
                    existing_point_vec = FreeCAD.Vector(key_tuple[0], key_tuple[1], key_tuple[2])
                    if (end_global - existing_point_vec).Length < tolerance:
                        found_end_key = key_tuple
                        break
                if found_end_key:
                    vertex_map[found_end_key].append((geo_index, 2))
                else:
                    vertex_map[end_global_tuple] = [(geo_index, 2)]

                constraint_index = final_sketch.addConstraint(Sketcher.Constraint('Block', geo_index))
                block_constraint_indices.append(constraint_index)

            coincident_constraints_added = 0
            for global_vertex_tuple, geo_vertex_pairs in vertex_map.items():
                if len(geo_vertex_pairs) > 1:
                    first_geo_index, first_vertex_id = geo_vertex_pairs[0]
                    for i in range(1, len(geo_vertex_pairs)):
                        next_geo_index, next_vertex_id = geo_vertex_pairs[i]
                        try:
                            final_sketch.addConstraint(Sketcher.Constraint('Coincident', first_geo_index, first_vertex_id, next_geo_index, next_vertex_id))
                            coincident_constraints_added += 1
                        except Exception as e:
                            FreeCAD.Console.PrintWarning(f"Could not add coincident constraint for {global_vertex_tuple}: {e}\n") 

            for c_idx in block_constraint_indices:
                try:
                    final_sketch.setVirtualSpace(c_idx, True)
                except Exception as e:
                    self.info_display.setText(f"Warning: Could not set visibility for constraint index {c_idx}: {e}")
                    FreeCAD.Console.PrintWarning(f"Could not set virtual space for constraint {c_idx}: {e}\n") 

            sketch_created_successfully = True
            doc.commitTransaction() 

        except Exception as e:
            self.info_display.setText(f"An error occurred during sketch creation:\n\n{e}")
            FreeCAD.Console.PrintError(f"Macro error: {e}\n") 
            doc.abortTransaction() 

        finally:
            if temp_sketch and hasattr(temp_sketch, 'Name'): # Robust check for temp_sketch
                try:
                    doc.removeObject(temp_sketch.Name)
                    doc.recompute() 
                except Exception as e:
                    FreeCAD.Console.PrintWarning(f"Could not remove temporary sketch: {e}\n") 

            if sketch_created_successfully and final_sketch:
                FreeCADGui.Selection.clearSelection()
                FreeCADGui.Selection.addSelection(final_sketch)
                FreeCADGui.activeDocument().activeView().viewAxonometric()
                FreeCADGui.activeDocument().activeView().fitAll()

                self.info_display.setText(f"Sketch created with correctly transformed construction geometry. Added {coincident_constraints_added} coincident constraints and hidden block constraints!")
                msg_success = QMessageBox()
                msg_success.setIcon(QMessageBox.Information)
                msg_success.setText("Sketch created successfully with chosen placement.")
                msg_success.setWindowTitle("Sketch Creation Success")
                msg_success.exec_()
            else:
                self.info_display.setText("Sketch creation failed or was cancelled.")

def show_edge_data_collector_docker():
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, EdgeDataCollector):
            widget.raise_()
            widget.activateWindow()
            return
    docker = EdgeDataCollector()
    FreeCADGui.getMainWindow().addDockWidget(Qt.RightDockWidgetArea, docker)

show_edge_data_collector_docker()
