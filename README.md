# CoplanarSketch FreeCAD Macro
![CoplanarSketch](https://github.com/user-attachments/assets/8447147a-78c9-40ff-8ce8-0d9e9e3bba24)

## Overview
The `CoplanarSketch` FreeCAD macro is a powerful tool designed to streamline the creation of sketches from existing 3D geometry, specifically focusing on **coplanar edges** found on tessellated solid bodies such as those converted from Mesh objects imported from STL files. It automates the process of identifying and selecting edges that lie on the same plane, then generates a new sketch containing these edges as construction geometry, correctly oriented in space.

![image](https://github.com/user-attachments/assets/88df8cf1-5ee3-4aa6-868f-9386a0d87e94)

## Features
* **Intelligent Coplanar Edge Selection**: Selects edges that share a common plane from a selected 3D object based on the actively selected face or by two coplanar edges.
* **Flexible Sketch Placement**: Offers multiple options for where the new sketch is created:
    * As a **standalone sketch** in the document's root (Part Workbench style).
    * Within a **newly created PartDesign Body**, with the sketch automatically attached to the body's XY plane.
    * Attached to the XY plane of an **existing PartDesign Body**, correctly nesting the sketch within the body in the model tree.
* **Construction Geometry**: All derived edges are added to the new sketch as construction geometry, providing a precise basis for further design without interfering with solid operations.
* **Robust Constraints**: Automatically applies block constraints to maintain the relative positions of the construction lines and adds coincident constraints where vertices are shared, ensuring stability.
* **User-Friendly Interface**: Provides a dockable GUI panel within FreeCAD for easy access to its functionalities.

## How to Use

1.  **Installation**:
    * Save the `CoplanarSketch.py` file into your FreeCAD Macros directory. You can find this directory by going to `Macros -> Macros...` in FreeCAD and checking the "User macros location" path.
    * (Optional but Recommended) Restart FreeCAD.

2.  **Running the Macro**:
    * Open a FreeCAD document containing a tessellated solid body.
    * Select the solid body (or specific edges/faces within it if desired).
    * Go to `Macros -> Macros...`.
    * Select `CoplanarSketch.py` from the list and click "Execute".
    * A dockable "Edge Data Collector" panel will appear.
    * Click "Collect Edge Data" (required for an initial scan of all edge data for the selected object).
    * Click "Select Coplanar Edges" to have the macro identify and select coplanar edges based on your initial selection (a face or two edges to define the plane).
    * Click "Create Sketch from Selection". A dialog will appear asking you to choose a placement option:
        * `<Standalone (Part Workbench)>`: Creates the sketch directly in the document root.
        * `<Create New Body (PartDesign)>`: Creates a new PartDesign Body and places the sketch inside it.
        * `[Existing Body Name]`: Places the sketch inside a selected existing PartDesign Body.
    * Choose your desired option and click "OK".

3.  **Post-Creation**:
    * The new sketch will be created and automatically selected in the tree view.
    * You can then enter the sketch to convert the construction to regular or add further geometry, dimensions, and constraints.

## Compatibility
This macro has been developed and tested with the following FreeCAD environment:
* **FreeCAD Version**: v1.0.1
* **Python Version**: 3.11.12
* **PySide Version**: 5.15.15 (Qt 5.15.15)
* **Operating System**: Windows 64-bit

While it may work on other versions or operating systems, compatibility is ensured for the listed environment.

## Contribution & Feedback
Feel free to open issues on this repository if you encounter any bugs or have suggestions for improvements.
