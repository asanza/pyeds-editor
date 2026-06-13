"""
PyCANopen EDS Editor
Copyright (C) 2026 Diego Asanza <f.asanza@gmail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
"""

import sys
import os
import json
import configparser
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QMenuBar, QMenu, QFileDialog, QMessageBox, QPushButton, QHeaderView,
    QInputDialog, QComboBox, QStyledItemDelegate, QListWidget, QListWidgetItem, QSplitter,
    QStackedWidget, QFormLayout, QLineEdit, QCheckBox, QGroupBox, QGridLayout, QDialog
)
from PySide6.QtCore import Qt
from pdo_mapper import PDOMapperDialog
from object_wizard import ObjectWizardDialog

class EDSParser(configparser.ConfigParser):
    def __init__(self, *args, **kwargs):
        kwargs['interpolation'] = None
        super().__init__(*args, **kwargs)

    # Override optionxform to preserve the case of keys
    def optionxform(self, optionstr):
        return optionstr

class PropertyDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        if index.column() == 1:
            table = index.model()
            key_index = table.index(index.row(), 0)
            key = table.data(key_index)
            
            if key == "DataType":
                editor = QComboBox(parent)
                editor.addItems(["0x0001 (boolean)", "0x0002 (int8)", "0x0003 (int16)", "0x0004 (int32)", 
                                 "0x0005 (uint8)", "0x0006 (uint16)", "0x0007 (uint32)", "0x0008 (real32)", "0x0009 (visible_string)"])
                return editor
            elif key == "AccessType":
                editor = QComboBox(parent)
                editor.addItems(["ro", "wo", "rw", "const"])
                return editor
            elif key == "ObjectType":
                editor = QComboBox(parent)
                editor.addItems(["0x7 (VAR)", "0x8 (ARRAY)", "0x9 (RECORD)"])
                return editor
                
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if isinstance(editor, QComboBox):
            text = index.model().data(index, Qt.EditRole)
            cb_index = editor.findText(text, Qt.MatchStartsWith)
            if cb_index >= 0:
                editor.setCurrentIndex(cb_index)
            else:
                editor.setCurrentText(text)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QComboBox):
            text = editor.currentText().split(" ")[0]
            model.setData(index, text, Qt.EditRole)
        else:
            super().setModelData(editor, model, index)

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.column() == 1:
            table = index.model()
            key_index = table.index(index.row(), 0)
            key = table.data(key_index)
            text = option.text
            
            if key == "DataType":
                mapping = {
                    "0x0001": "0x0001 (boolean)", "0x0002": "0x0002 (int8)", "0x0003": "0x0003 (int16)", "0x0004": "0x0004 (int32)",
                    "0x0005": "0x0005 (uint8)", "0x0006": "0x0006 (uint16)", "0x0007": "0x0007 (uint32)", "0x0008": "0x0008 (real32)",
                    "0x0009": "0x0009 (visible_string)", "0x000a": "0x000A (octet_string)", "0x000b": "0x000B (unicode_string)",
                    "0x000c": "0x000C (time_of_day)", "0x000d": "0x000D (time_difference)", "0x000f": "0x000F (domain)",
                    "0x0020": "0x0020 (int64)", "0x0021": "0x0021 (uint64)"
                }
                val = text.strip().lower()
                if val.startswith("0x") and len(val) < 6:
                    val = "0x" + val[2:].zfill(4)
                if val in mapping:
                    option.text = mapping[val]
            elif key == "ObjectType":
                mapping = {
                    "0x7": "0x7 (VAR)", "0x07": "0x7 (VAR)",
                    "0x8": "0x8 (ARRAY)", "0x08": "0x8 (ARRAY)",
                    "0x9": "0x9 (RECORD)", "0x09": "0x9 (RECORD)"
                }
                val = text.strip().lower()
                if val in mapping:
                    option.text = mapping[val]


class DeviceInfoWidget(QWidget):
    def __init__(self, parser):
        super().__init__()
        self.parser = parser
        self.updating = False
        
        layout = QVBoxLayout(self)
        
        # General Info
        general_group = QGroupBox("General Information")
        general_layout = QFormLayout(general_group)
        
        self.vendor_name = QLineEdit()
        self.vendor_number = QLineEdit()
        self.product_name = QLineEdit()
        self.product_number = QLineEdit()
        
        general_layout.addRow("Vendor Name:", self.vendor_name)
        general_layout.addRow("Vendor Number:", self.vendor_number)
        general_layout.addRow("Product Name:", self.product_name)
        general_layout.addRow("Product Number:", self.product_number)
        layout.addWidget(general_group)
        
        # Baud Rates
        baud_group = QGroupBox("Supported Baud Rates")
        baud_layout = QGridLayout(baud_group)
        self.baud_boxes = {}
        baud_rates = ["10", "20", "50", "125", "250", "500", "800", "1000"]
        for i, rate in enumerate(baud_rates):
            cb = QCheckBox(f"{rate} kbps")
            self.baud_boxes[f"BaudRate_{rate}"] = cb
            baud_layout.addWidget(cb, i // 4, i % 4)
            cb.stateChanged.connect(lambda state, k=f"BaudRate_{rate}": self.on_field_changed(k, "1" if state else "0"))
            
        layout.addWidget(baud_group)
        
        # Features
        features_group = QGroupBox("Features")
        features_layout = QFormLayout(features_group)
        self.lss_supported = QCheckBox("LSS Supported")
        self.lss_supported.stateChanged.connect(lambda state: self.on_field_changed("LSS_Supported", "1" if state else "0"))
        features_layout.addRow(self.lss_supported)
        layout.addWidget(features_group)
        
        layout.addStretch()

        self.vendor_name.textChanged.connect(lambda t: self.on_field_changed("VendorName", t))
        self.vendor_number.textChanged.connect(lambda t: self.on_field_changed("VendorNumber", t))
        self.product_name.textChanged.connect(lambda t: self.on_field_changed("ProductName", t))
        self.product_number.textChanged.connect(lambda t: self.on_field_changed("ProductNumber", t))

    def load_data(self):
        self.updating = True
        
        if not self.parser.has_section("DeviceInfo"):
            self.updating = False
            return
            
        self.vendor_name.setText(self.parser.get("DeviceInfo", "VendorName", fallback=""))
        self.vendor_number.setText(self.parser.get("DeviceInfo", "VendorNumber", fallback=""))
        self.product_name.setText(self.parser.get("DeviceInfo", "ProductName", fallback=""))
        self.product_number.setText(self.parser.get("DeviceInfo", "ProductNumber", fallback=""))
        
        for key, cb in self.baud_boxes.items():
            val = self.parser.get("DeviceInfo", key, fallback="0")
            cb.setChecked(val == "1")
            
        lss = self.parser.get("DeviceInfo", "LSS_Supported", fallback="0")
        self.lss_supported.setChecked(lss == "1")
        
        self.updating = False
        
    def on_field_changed(self, key, value):
        if self.updating: return
        if not self.parser.has_section("DeviceInfo"):
            self.parser.add_section("DeviceInfo")
        self.parser.set("DeviceInfo", key, value)

class EDSEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CANopen EDS Editor")
        self.resize(1000, 600)
        
        self.current_file = None
        self.parser = EDSParser()
        
        self.init_ui()
        
    def init_ui(self):
        # Menu Bar
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        
        self.new_device_menu = file_menu.addMenu("New Device")
        self.load_profiles_menu()

        open_action = file_menu.addAction("Open EDS")
        open_action.triggered.connect(self.open_file)
        
        save_action = file_menu.addAction("Save EDS")
        save_action.triggered.connect(self.save_file)
        
        save_as_action = file_menu.addAction("Save As...")
        save_as_action.triggered.connect(self.save_file_as)
        
        file_menu.addSeparator()
        exit_action = file_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

        tools_menu = menu_bar.addMenu("Tools")
        validate_action = tools_menu.addAction("Validate EDS")
        validate_action.triggered.connect(self.validate_eds)
        
        report_action = tools_menu.addAction("Generate HTML Report")
        report_action.triggered.connect(self.generate_report)
        
        c_export_action = tools_menu.addAction("Export to C/H Files")
        c_export_action.triggered.connect(self.generate_c_export)
        
        tools_menu.addSeparator()
        pdo_action = tools_menu.addAction("Visual PDO Mapper")
        pdo_action.triggered.connect(self.open_pdo_mapper)
        
        wizard_action = tools_menu.addAction("Smart Object Wizard")
        wizard_action.triggered.connect(self.open_object_wizard)

        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(splitter)
        
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left side: Tree view of sections
        left_layout = QVBoxLayout()
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabel("Sections (Objects)")
        self.tree_widget.currentItemChanged.connect(self.on_section_selected)
        
        btn_add_section = QPushButton("Add Section")
        btn_add_section.clicked.connect(self.add_section)
        
        left_layout.addWidget(self.tree_widget)
        left_layout.addWidget(btn_add_section)
        
        # Right side: Stacked widget
        self.right_stack = QStackedWidget()
        
        # Stack 0: Table view of properties
        self.table_container = QWidget()
        table_layout = QVBoxLayout(self.table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(2)
        self.table_widget.setHorizontalHeaderLabels(["Key", "Value"])
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_widget.setItemDelegate(PropertyDelegate(self))
        self.table_widget.itemChanged.connect(self.on_item_changed)
        
        btn_add_property = QPushButton("Add Property")
        btn_add_property.clicked.connect(self.add_property)
        
        table_layout.addWidget(self.table_widget)
        table_layout.addWidget(btn_add_property)
        
        # Stack 1: Device Info Widget
        self.device_info_widget = DeviceInfoWidget(self.parser)
        
        self.right_stack.addWidget(self.table_container)
        self.right_stack.addWidget(self.device_info_widget)
        
        # Set layout proportions
        top_layout.addLayout(left_layout, 1)
        top_layout.addWidget(self.right_stack, 2)
        
        self.validation_list = QListWidget()
        self.validation_list.setMaximumHeight(150)
        
        splitter.addWidget(top_widget)
        splitter.addWidget(self.validation_list)
        
        self.current_section = None
        self.updating_table = False

    def validate_eds(self):
        self.validation_list.clear()
        warnings = []
        
        mandatory_sections = ["FileInfo", "DeviceInfo", "1000", "1001", "1018"]
        for sec in mandatory_sections:
            if not self.parser.has_section(sec):
                warnings.append(f"CRITICAL: Missing mandatory section [{sec}]")
                
        if self.parser.has_section("1018"):
            sub_count = self.parser.get("1018", "SubNumber", fallback=None)
            if not sub_count:
                warnings.append("WARNING: [1018] Identity Object is missing 'SubNumber'")
            else:
                try:
                    count = int(sub_count)
                    for i in range(count + 1):
                        sub_sec = f"1018sub{i}"
                        if not self.parser.has_section(sub_sec):
                            warnings.append(f"WARNING: Identity Object declares {count} sub-items but [{sub_sec}] is missing.")
                except ValueError:
                    warnings.append("WARNING: [1018] 'SubNumber' is not a valid integer.")
                    
        for section in self.parser.sections():
            if section.isdigit() or "sub" in section:
                if not self.parser.has_option(section, "ParameterName"):
                    warnings.append(f"INFO: [{section}] is missing 'ParameterName'")
                if not self.parser.has_option(section, "ObjectType"):
                    warnings.append(f"WARNING: [{section}] is missing 'ObjectType'")
                    
        if not warnings:
            self.validation_list.addItem("✅ EDS Validation Passed! No obvious issues found.")
        else:
            self.validation_list.addItem(f"⚠️ Validation finished with {len(warnings)} issues:")
            for w in warnings:
                item = QListWidgetItem(w)
                if w.startswith("CRITICAL"):
                    item.setForeground(Qt.red)
                elif w.startswith("WARNING"):
                    item.setForeground(Qt.darkYellow)
                self.validation_list.addItem(item)

    def generate_report(self):
        if not self.parser.sections():
            QMessageBox.warning(self, "Error", "No EDS data to report on.")
            return
            
        file_name, _ = QFileDialog.getSaveFileName(self, "Save HTML Report", "eds_report.html", "HTML Files (*.html)")
        if not file_name:
            return
            
        html = [
            "<html><head><style>",
            "body { font-family: sans-serif; margin: 2rem; background: #f4f4f9; color: #333; }",
            "h1 { color: #0056b3; }",
            "table { border-collapse: collapse; width: 100%; margin-bottom: 2rem; background: white; }",
            "th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }",
            "th { background-color: #0056b3; color: white; }",
            "tr:nth-child(even) { background-color: #f2f2f2; }",
            "</style></head><body>",
            f"<h1>CANopen EDS Report</h1>"
        ]
        
        # Device Info
        html.append("<h2>Device Information</h2><table><tr><th>Property</th><th>Value</th></tr>")
        if self.parser.has_section("DeviceInfo"):
            for k, v in self.parser.items("DeviceInfo"):
                html.append(f"<tr><td>{k}</td><td>{v}</td></tr>")
        html.append("</table>")
        
        # Object Dictionary
        html.append("<h2>Object Dictionary</h2><table><tr><th>Index</th><th>Name</th><th>Type</th><th>Access</th><th>Default</th></tr>")
        
        for sec in sorted(self.parser.sections()):
            if sec in ["FileInfo", "DeviceInfo", "Comments", "DummyUsage"]: continue
            
            name = self.parser.get(sec, "ParameterName", fallback="")
            obj_type = self.parser.get(sec, "ObjectType", fallback="")
            access = self.parser.get(sec, "AccessType", fallback="")
            default = self.parser.get(sec, "DefaultValue", fallback="")
            
            html.append(f"<tr><td><b>{sec}</b></td><td>{name}</td><td>{obj_type}</td><td>{access}</td><td>{default}</td></tr>")
            
        html.append("</table>")
        
        # PDO Memory Maps
        html.append("<h2>PDO Memory Maps</h2>")
        
        def render_pdo_table(base_idx, title_prefix):
            for i in range(32):
                map_idx = f"{base_idx + i:04X}"
                if self.parser.has_section(map_idx):
                    html.append(f"<h3>{title_prefix} {i+1} (0x{map_idx})</h3>")
                    html.append("<table><tr><th>Offset (Bits)</th><th>Mapped Object</th><th>Name</th><th>Length</th></tr>")
                    
                    sub_count_str = self.parser.get(map_idx, "SubNumber", fallback="0")
                    try: sub_count = int(sub_count_str)
                    except: sub_count = 0
                    
                    bit_offset = 0
                    for s in range(1, sub_count + 1):
                        sub_sec = f"{map_idx}sub{s}"
                        if self.parser.has_section(sub_sec):
                            default_val = self.parser.get(sub_sec, "DefaultValue", fallback="0x00000000")
                            try:
                                val_int = int(default_val, 16)
                                if val_int == 0: continue
                                length = val_int & 0xFF
                                sub_idx = (val_int >> 8) & 0xFF
                                obj_idx = (val_int >> 16) & 0xFFFF
                                
                                # Resolve name
                                target_name = "Unknown Object"
                                # Try with subindex formatting
                                target_sec = f"{obj_idx:04X}sub{sub_idx:02X}"
                                if self.parser.has_section(target_sec):
                                    target_name = self.parser.get(target_sec, "ParameterName", fallback="Unknown Object")
                                elif self.parser.has_section(target_sec.upper()):
                                    target_name = self.parser.get(target_sec.upper(), "ParameterName", fallback="Unknown Object")
                                elif self.parser.has_section(target_sec.lower()):
                                    target_name = self.parser.get(target_sec.lower(), "ParameterName", fallback="Unknown Object")
                                else:
                                    # Try just the index (if sub0)
                                    target_sec_no_sub = f"{obj_idx:04X}"
                                    if self.parser.has_section(target_sec_no_sub):
                                        target_name = self.parser.get(target_sec_no_sub, "ParameterName", fallback="Unknown Object")
                                        
                                html.append(f"<tr><td><b>{bit_offset}</b></td><td>0x{obj_idx:04X}sub{sub_idx:02X}</td><td>{target_name}</td><td>{length} bits</td></tr>")
                                bit_offset += length
                            except ValueError:
                                pass
                    html.append("</table>")
            
        render_pdo_table(0x1600, "Receive PDO (RPDO)")
        render_pdo_table(0x1A00, "Transmit PDO (TPDO)")
        
        html.append("</body></html>")
        
        try:
            with open(file_name, "w") as f:
                f.write("\n".join(html))
            QMessageBox.information(self, "Success", f"Report saved to {file_name}")
            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(file_name)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to write report:\n{str(e)}")

    def open_pdo_mapper(self):
        if not self.parser.sections():
            QMessageBox.warning(self, "Error", "No EDS data loaded.")
            return
            
        dialog = PDOMapperDialog(self.parser, self)
        if dialog.exec() == QDialog.Accepted:
            self.load_eds_data()
            if self.current_section:
                self.populate_table(self.current_section)

    def open_object_wizard(self):
        if not self.parser.sections():
            QMessageBox.warning(self, "Error", "No EDS data loaded. Create or Open an EDS first.")
            return
            
        dialog = ObjectWizardDialog(self.parser, self)
        if dialog.exec() == QDialog.Accepted:
            self.load_eds_data()

    def generate_c_export(self):
        if not self.parser.sections():
            QMessageBox.warning(self, "Error", "No EDS data to export.")
            return
            
        dir_name = QFileDialog.getExistingDirectory(self, "Select Directory to Save C/H Files")
        if not dir_name:
            return
            
        type_map = {
            "0x0001": "bool", "0x0002": "int8_t", "0x0003": "int16_t", "0x0004": "int32_t",
            "0x0005": "uint8_t", "0x0006": "uint16_t", "0x0007": "uint32_t", "0x0008": "float"
        }
        
        def clean_name(name, default="unnamed"):
            if not name: return default
            import re
            clean = re.sub(r'\W+', '_', name).strip('_').lower()
            return clean if clean else default

        h_lines = [
            "/**",
            " * CANopen Object Dictionary Header",
            " * Auto-generated by PyCANopen Editor",
            " */",
            "#ifndef OD_H",
            "#define OD_H",
            "",
            "#include <stdint.h>",
            "#include <stdbool.h>",
            "",
            "typedef struct {"
        ]
        
        c_lines = [
            "/**",
            " * CANopen Object Dictionary Source",
            " * Auto-generated by PyCANopen Editor",
            " */",
            "#include \"OD.h\"",
            "",
            "OD_t OD = {"
        ]
        
        parents = []
        for sec in sorted(self.parser.sections()):
            if sec in ["FileInfo", "DeviceInfo", "Comments", "DummyUsage"]: continue
            if "sub" not in sec.lower():
                parents.append(sec)
                
        for p in parents:
            obj_type = self.parser.get(p, "ObjectType", fallback="0x7").lower()
            name = self.parser.get(p, "ParameterName", fallback=f"obj_{p}")
            c_name = clean_name(name)
            
            if obj_type in ["0x7", "0x07"]:
                dt = self.parser.get(p, "DataType", fallback="0x0007").lower()
                default_val = self.parser.get(p, "DefaultValue", fallback="0")
                if not default_val: default_val = "0"
                if dt.startswith("0x") and len(dt) < 6:
                    dt = "0x" + dt[2:].zfill(4)
                c_type = type_map.get(dt, "uint32_t")
                
                h_lines.append(f"    {c_type} {c_name}; // 0x{p}")
                c_lines.append(f"    .{c_name} = {default_val},")
                
            elif obj_type in ["0x8", "0x08", "0x9", "0x09"]:
                h_lines.append(f"    struct {{")
                c_lines.append(f"    .{c_name} = {{")
                
                sub_count_str = self.parser.get(p, "SubNumber", fallback="0")
                try:
                    sub_count = int(sub_count_str)
                except ValueError:
                    sub_count = 0
                    
                for i in range(sub_count + 1):
                    sub_sec = f"{p}sub{i}"
                    if self.parser.has_section(sub_sec):
                        sub_name = self.parser.get(sub_sec, "ParameterName", fallback=f"sub{i}")
                        sub_dt = self.parser.get(sub_sec, "DataType", fallback="0x0007").lower()
                        default_val = self.parser.get(sub_sec, "DefaultValue", fallback="0")
                        if not default_val: default_val = "0"
                        if sub_dt.startswith("0x") and len(sub_dt) < 6:
                            sub_dt = "0x" + sub_dt[2:].zfill(4)
                        sub_c_name = clean_name(sub_name)
                        sub_c_type = type_map.get(sub_dt, "uint32_t")
                        
                        h_lines.append(f"        {sub_c_type} {sub_c_name}; // 0x{p} sub {i}")
                        c_lines.append(f"        .{sub_c_name} = {default_val},")
                        
                h_lines.append(f"    }} {c_name}; // 0x{p}")
                c_lines.append(f"    }},")
                
        h_lines.append("} OD_t;")
        h_lines.append("")
        h_lines.append("extern OD_t OD;")
        h_lines.append("")
        h_lines.append("#endif // OD_H")
        
        c_lines.append("};")
        
        # --- Add Metadata Routing Table ---
        c_lines.append("")
        c_lines.append("/**")
        c_lines.append(" * Generic Object Dictionary Routing Table")
        c_lines.append(" */")
        c_lines.append("typedef struct {")
        c_lines.append("    uint16_t index;")
        c_lines.append("    uint8_t subIndex;")
        c_lines.append("    uint8_t is_rw; // 1 = RW, 0 = RO")
        c_lines.append("    uint16_t length;")
        c_lines.append("    void *pData;")
        c_lines.append("} OD_entry_t;")
        c_lines.append("")
        c_lines.append("const OD_entry_t OD_dictionary[] = {")
        
        for p in parents:
            obj_type = self.parser.get(p, "ObjectType", fallback="0x7").lower()
            name = self.parser.get(p, "ParameterName", fallback=f"obj_{p}")
            c_name = clean_name(name)
            
            if obj_type in ["0x7", "0x07"]:
                dt = self.parser.get(p, "DataType", fallback="0x0007").lower()
                if dt.startswith("0x") and len(dt) < 6: dt = "0x" + dt[2:].zfill(4)
                c_type = type_map.get(dt, "uint32_t")
                access = "1" if self.parser.get(p, "AccessType", fallback="ro").lower() in ["rw", "rww"] else "0"
                c_lines.append(f"    {{ 0x{p}, 0x00, {access}, sizeof({c_type}), &OD.{c_name} }},")
                
            elif obj_type in ["0x8", "0x08", "0x9", "0x09"]:
                sub_count_str = self.parser.get(p, "SubNumber", fallback="0")
                try: sub_count = int(sub_count_str)
                except ValueError: sub_count = 0
                    
                for i in range(sub_count + 1):
                    sub_sec = f"{p}sub{i}"
                    if self.parser.has_section(sub_sec):
                        sub_name = self.parser.get(sub_sec, "ParameterName", fallback=f"sub{i}")
                        sub_dt = self.parser.get(sub_sec, "DataType", fallback="0x0007").lower()
                        if sub_dt.startswith("0x") and len(sub_dt) < 6: sub_dt = "0x" + sub_dt[2:].zfill(4)
                        sub_c_name = clean_name(sub_name)
                        sub_c_type = type_map.get(sub_dt, "uint32_t")
                        access = "1" if self.parser.get(sub_sec, "AccessType", fallback="ro").lower() in ["rw", "rww"] else "0"
                        c_lines.append(f"    {{ 0x{p}, 0x{i:02X}, {access}, sizeof({sub_c_type}), &OD.{c_name}.{sub_c_name} }},")
                        
        c_lines.append("};")
        c_lines.append("")
        c_lines.append("const uint32_t OD_dictionary_size = sizeof(OD_dictionary) / sizeof(OD_entry_t);")
        
        try:
            h_file = os.path.join(dir_name, "OD.h")
            c_file = os.path.join(dir_name, "OD.c")
            with open(h_file, "w") as f:
                f.write("\n".join(h_lines))
            with open(c_file, "w") as f:
                f.write("\n".join(c_lines))
            QMessageBox.information(self, "Success", f"C/H Files saved to {dir_name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to write C files:\n{str(e)}")

    def load_eds_data(self):
        self.tree_widget.clear()
        self.table_widget.setRowCount(0)
        
        parent_nodes = {}
        
        # First pass: create top-level parent nodes
        for section in self.parser.sections():
            if "sub" not in section.lower():
                name = self.parser.get(section, "ParameterName", fallback="")
                display_text = f"[{section}] {name}" if name else section
                item = QTreeWidgetItem([display_text])
                item.setData(0, Qt.UserRole, section)
                self.tree_widget.addTopLevelItem(item)
                parent_nodes[section.lower()] = item
                
        # Second pass: attach sub-items to their parents
        for section in self.parser.sections():
            if "sub" in section.lower():
                parent_key = section.lower().split("sub")[0]
                
                name = self.parser.get(section, "ParameterName", fallback="")
                display_text = f"[{section}] {name}" if name else section
                item = QTreeWidgetItem([display_text])
                item.setData(0, Qt.UserRole, section)
                
                if parent_key in parent_nodes:
                    parent_nodes[parent_key].addChild(item)
                else:
                    self.tree_widget.addTopLevelItem(item)

    def on_section_selected(self, current, previous):
        if not current:
            return
            
        section_name = current.data(0, Qt.UserRole)
        if not section_name:
            section_name = current.text(0)
            
        self.current_section = section_name
        
        if section_name == "DeviceInfo":
            self.right_stack.setCurrentIndex(1)
            self.device_info_widget.load_data()
        else:
            self.right_stack.setCurrentIndex(0)
            self.populate_table(section_name)

    def populate_table(self, section_name):
        self.updating_table = True
        self.table_widget.setRowCount(0)
        
        if self.parser.has_section(section_name):
            items = self.parser.items(section_name)
            self.table_widget.setRowCount(len(items))
            for row, (key, value) in enumerate(items):
                key_item = QTableWidgetItem(key)
                key_item.setFlags(key_item.flags() & ~Qt.ItemIsEditable) # Key is read-only for simplicity
                val_item = QTableWidgetItem(value)
                
                self.table_widget.setItem(row, 0, key_item)
                self.table_widget.setItem(row, 1, val_item)
                
        self.updating_table = False

    def on_item_changed(self, item):
        if self.updating_table or not self.current_section:
            return
            
        row = item.row()
        col = item.column()
        
        if col == 1: # Value changed
            key = self.table_widget.item(row, 0).text()
            new_value = item.text()
            self.parser.set(self.current_section, key, new_value)

    def add_section(self):
        section_name, ok = QInputDialog.getText(self, "Add Section", "Section Name (e.g., 1000 or 1018sub1):")
        if ok and section_name:
            if not self.parser.has_section(section_name):
                self.parser.add_section(section_name)
                item = QTreeWidgetItem([section_name])
                self.tree_widget.addTopLevelItem(item)
                self.tree_widget.setCurrentItem(item)
            else:
                QMessageBox.warning(self, "Error", f"Section '{section_name}' already exists.")

    def add_property(self):
        if not self.current_section:
            QMessageBox.warning(self, "Error", "Please select a section first.")
            return
            
        key, ok = QInputDialog.getText(self, "Add Property", "Property Name (Key):")
        if ok and key:
            if not self.parser.has_option(self.current_section, key):
                self.parser.set(self.current_section, key, "")
                self.populate_table(self.current_section)
            else:
                QMessageBox.warning(self, "Error", f"Property '{key}' already exists.")

    def open_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open EDS File", "", "EDS Files (*.eds);;INI Files (*.ini);;All Files (*)")
        if file_name:
            try:
                self.parser = EDSParser()
                self.parser.read(file_name)
                self.current_file = file_name
                self.load_eds_data()
                self.setWindowTitle(f"CANopen EDS Editor - {self.current_file}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to read file:\n{str(e)}")

    def load_profiles_menu(self):
        self.new_device_menu.clear()
        self.profiles = {}
        
        profiles_dir = "profiles"
        if os.path.exists(profiles_dir):
            for filename in os.listdir(profiles_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(profiles_dir, filename)
                    try:
                        with open(filepath, "r") as f:
                            profile_data = json.load(f)
                            profile_id = profile_data.get("id")
                            profile_name = profile_data.get("name")
                            if profile_id and profile_name:
                                self.profiles[profile_id] = profile_data
                                action = self.new_device_menu.addAction(f"{profile_name} (CiA {profile_id})")
                                action.triggered.connect(lambda checked=False, pid=profile_id: self.new_device(pid))
                    except Exception as e:
                        print(f"Failed to load profile {filename}: {e}")

    def new_device(self, profile_id):
        self.parser = EDSParser()
        self.current_file = None
        self.setWindowTitle(f"CANopen EDS Editor - Unnamed Device (CiA {profile_id})")
        
        # Add basic FileInfo and DeviceInfo
        self.parser.add_section("FileInfo")
        self.parser.set("FileInfo", "FileName", "unnamed.eds")
        self.parser.set("FileInfo", "FileVersion", "1")
        self.parser.set("FileInfo", "FileRevision", "1")
        
        self.parser.add_section("DeviceInfo")
        self.parser.set("DeviceInfo", "VendorName", "My Vendor")
        self.parser.set("DeviceInfo", "ProductName", "My Device")
        
        # Always add 301 objects first if we are not creating 301 and it exists
        if profile_id != "301" and "301" in self.profiles:
            self._apply_profile("301")
            
        self._apply_profile(profile_id)
        self.load_eds_data()

    def _apply_profile(self, profile_id):
        profile_data = self.profiles.get(profile_id)
        if not profile_data:
            return
            
        objects = profile_data.get("objects", {})
        for obj_idx, properties in objects.items():
            if not self.parser.has_section(obj_idx):
                self.parser.add_section(obj_idx)
            for k, v in properties.items():
                self.parser.set(obj_idx, k, str(v))

    def save_file(self):
        if self.current_file:
            self._save(self.current_file)
        else:
            self.save_file_as()

    def save_file_as(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Save EDS File", "", "EDS Files (*.eds);;All Files (*)")
        if file_name:
            self._save(file_name)
            self.current_file = file_name
            self.setWindowTitle(f"CANopen EDS Editor - {self.current_file}")

    def _save(self, file_name):
        try:
            with open(file_name, 'w') as configfile:
                self.parser.write(configfile, space_around_delimiters=False)
            QMessageBox.information(self, "Success", "File saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file:\n{str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = EDSEditor()
    window.show()
    sys.exit(app.exec())
