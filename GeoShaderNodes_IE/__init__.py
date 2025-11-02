bl_info = {
    "name": "GeoNodes IE & ShaderNodes IE",
    "blender": (4, 0, 0),
    "category": "Node",
    "description": "Exporter et importer Geometry Nodes et Shader Nodes avec leurs propriétés et connexions",
    "author": "David Savini (code GPT)",
    "version": (1, 2),
}

import bpy
import os
import json
from mathutils import Vector, Euler, Color


# =====================
# Utils
# =====================
def serialize_value(value):
    if isinstance(value, (bpy.types.bpy_prop_array, tuple, list)):
        return list(value)
    elif isinstance(value, (Vector, Euler)):
        return list(value[:])
    elif isinstance(value, Color):
        return [value.r, value.g, value.b, getattr(value, "a", 1.0)]
    elif isinstance(value, (int, float, str, bool)):
        return value
    return None


def restore_value(prop_owner, prop, value):
    try:
        if isinstance(getattr(prop_owner, prop), (Vector, Euler, Color)):
            setattr(prop_owner, prop, type(getattr(prop_owner, prop))(value))
        else:
            setattr(prop_owner, prop, value)
    except Exception:
        pass


def get_export_path(context, filename):
    """Retourne le chemin d’export basé sur les préférences utilisateur"""
    prefs = context.preferences.addons[__name__].preferences
    folder = prefs.export_directory
    return os.path.join(folder, filename)


# =====================
# Export / Import générique
# =====================
def export_nodes(node_tree, filepath, block_name):
    all_data = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except json.JSONDecodeError:
            pass

    node_data = []
    link_data = []
    selected_nodes = [n for n in node_tree.nodes if n.select]

    for node in selected_nodes:
        properties = {}
        # propriétés directes
        for prop in node.bl_rna.properties:
            if not prop.is_readonly and not prop.identifier.startswith("bl_"):
                try:
                    val = serialize_value(getattr(node, prop.identifier))
                    if val is not None:
                        properties[prop.identifier] = val
                except:
                    pass
        # sockets
        for input_socket in node.inputs:
            if hasattr(input_socket, "default_value") and not input_socket.is_linked:
                properties[input_socket.identifier] = serialize_value(input_socket.default_value)

        node_data.append({
            "name": node.name,
            "type": node.bl_idname,
            "location": list(node.location),
            "properties": properties,
        })

    for link in node_tree.links:
        if link.from_node in selected_nodes and link.to_node in selected_nodes:
            link_data.append({
                "from_node": link.from_node.name,
                "from_socket": link.from_socket.name,
                "to_node": link.to_node.name,
                "to_socket": link.to_socket.name,
            })

    all_data[block_name] = {"nodes": node_data, "links": link_data}

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=4)


def import_nodes(node_tree, filepath, block_name):
    if not os.path.exists(filepath):
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        all_data = json.load(f)
    data = all_data.get(block_name, {})

    node_map = {}
    for node_info in data.get("nodes", []):
        new_node = node_tree.nodes.new(type=node_info["type"])
        new_node.name, new_node.location = node_info["name"], node_info["location"]
        for prop, value in node_info["properties"].items():
            if hasattr(new_node, prop):
                restore_value(new_node, prop, value)
            else:
                # peut-être un input socket
                sock = new_node.inputs.get(prop)
                if sock and hasattr(sock, "default_value"):
                    try:
                        sock.default_value = value
                    except:
                        pass
        node_map[node_info["name"]] = new_node

    for link_info in data.get("links", []):
        fn, tn = node_map.get(link_info["from_node"]), node_map.get(link_info["to_node"])
        if fn and tn:
            fs = next((s for s in fn.outputs if s.name == link_info["from_socket"]), None)
            ts = next((s for s in tn.inputs if s.name == link_info["to_socket"]), None)
            if fs and ts:
                node_tree.links.new(fs, ts)

    return True


# =====================
# Geometry Nodes
# =====================
class NODE_OT_export_geo(bpy.types.Operator):
    bl_idname = "node.export_geo_nodes"
    bl_label = "Exporter GeoNodes"

    name: bpy.props.StringProperty(name="Nom du bloc")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        node_tree = context.space_data.node_tree
        if not node_tree or node_tree.bl_idname != "GeometryNodeTree":
            self.report({"ERROR"}, "Veuillez être dans un éditeur Geometry Nodes.")
            return {"CANCELLED"}
        filepath = get_export_path(context, "export_geometry_nodes.json")
        export_nodes(node_tree, filepath, self.name)
        self.report({"INFO"}, f"GeoNodes exportés : {self.name}")
        return {"FINISHED"}


class NODE_OT_import_geo(bpy.types.Operator):
    bl_idname = "node.import_geo_nodes"
    bl_label = "Importer GeoNodes"

    def geo_list(self, context):
        filepath = get_export_path(context, "export_geometry_nodes.json")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    return [(k, k, "") for k in data.keys()]
                except:
                    pass
        return [("NONE", "Aucun bloc", "")]

    group_name: bpy.props.EnumProperty(name="Bloc GeoNodes", items=geo_list)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if self.group_name == "NONE":
            return {"CANCELLED"}
        node_tree = context.space_data.node_tree
        filepath = get_export_path(context, "export_geometry_nodes.json")
        if import_nodes(node_tree, filepath, self.group_name):
            self.report({"INFO"}, f"GeoNodes importés : {self.group_name}")
        return {"FINISHED"}


class NODE_MT_geo_menu(bpy.types.Menu):
    bl_label = "GeoNodes IE"
    bl_idname = "NODE_MT_geo_menu"

    def draw(self, context):
        layout = self.layout
        layout.operator("node.export_geo_nodes")
        layout.operator("node.import_geo_nodes")


def draw_geo_menu(self, context):
    if context.space_data.tree_type == "GeometryNodeTree":
        self.layout.menu("NODE_MT_geo_menu")


# =====================
# Shader Nodes
# =====================
class NODE_OT_export_shader(bpy.types.Operator):
    bl_idname = "node.export_shader_nodes"
    bl_label = "Exporter ShaderNodes"

    name: bpy.props.StringProperty(name="Nom du bloc")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        node_tree = context.space_data.node_tree
        if not node_tree or node_tree.bl_idname != "ShaderNodeTree":
            self.report({"ERROR"}, "Veuillez être dans un éditeur Shader Nodes.")
            return {"CANCELLED"}
        filepath = get_export_path(context, "export_shader_nodes.json")
        export_nodes(node_tree, filepath, self.name)
        self.report({"INFO"}, f"ShaderNodes exportés : {self.name}")
        return {"FINISHED"}


class NODE_OT_import_shader(bpy.types.Operator):
    bl_idname = "node.import_shader_nodes"
    bl_label = "Importer ShaderNodes"

    def shader_list(self, context):
        filepath = get_export_path(context, "export_shader_nodes.json")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    return [(k, k, "") for k in data.keys()]
                except:
                    pass
        return [("NONE", "Aucun bloc", "")]

    group_name: bpy.props.EnumProperty(name="Bloc ShaderNodes", items=shader_list)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if self.group_name == "NONE":
            return {"CANCELLED"}
        node_tree = context.space_data.node_tree
        filepath = get_export_path(context, "export_shader_nodes.json")
        if import_nodes(node_tree, filepath, self.group_name):
            self.report({"INFO"}, f"ShaderNodes importés : {self.group_name}")
        return {"FINISHED"}


class NODE_MT_shader_menu(bpy.types.Menu):
    bl_label = "ShaderNodes IE"
    bl_idname = "NODE_MT_shader_menu"

    def draw(self, context):
        layout = self.layout
        layout.operator("node.export_shader_nodes")
        layout.operator("node.import_shader_nodes")


def draw_shader_menu(self, context):
    if context.space_data.tree_type == "ShaderNodeTree":
        self.layout.menu("NODE_MT_shader_menu")


# =====================
# Add-on Preferences
# =====================
class GNIEPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    export_directory: bpy.props.StringProperty(
        name="Dossier d'export",
        subtype='DIR_PATH',
        default=os.path.join(os.path.expanduser("~"), "Desktop"),
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Chemin d’export par défaut")
        layout.prop(self, "export_directory")


# =====================
# Register
# =====================
classes = [
    NODE_OT_export_geo, NODE_OT_import_geo, NODE_MT_geo_menu,
    NODE_OT_export_shader, NODE_OT_import_shader, NODE_MT_shader_menu,
    GNIEPreferences
]

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.NODE_MT_editor_menus.append(draw_geo_menu)
    bpy.types.NODE_MT_editor_menus.append(draw_shader_menu)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    bpy.types.NODE_MT_editor_menus.remove(draw_geo_menu)
    bpy.types.NODE_MT_editor_menus.remove(draw_shader_menu)

if __package__ == "__main__":
    register()
