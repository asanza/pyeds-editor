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

import configparser
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QSpinBox,
    QDialogButtonBox, QMessageBox
)

class ObjectWizardDialog(QDialog):
    def __init__(self, parser, parent=None):
        super().__init__(parent)
        self.parser = parser
        self.setWindowTitle("Smart Object Wizard")
        self.resize(350, 200)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.idx_input = QLineEdit()
        self.idx_input.setPlaceholderText("e.g. 2000")
        form.addRow("Index (Hex):", self.idx_input)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("My Custom Array")
        form.addRow("Parameter Name:", self.name_input)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems(["ARRAY (0x8)", "RECORD (0x9)"])
        form.addRow("Object Type:", self.type_combo)
        
        self.dt_combo = QComboBox()
        self.dt_combo.addItems([
            "0x0001 (boolean)", "0x0002 (int8)", "0x0003 (int16)", "0x0004 (int32)",
            "0x0005 (uint8)", "0x0006 (uint16)", "0x0007 (uint32)", "0x0008 (real32)"
        ])
        form.addRow("Sub-Items Data Type:", self.dt_combo)
        
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 255)
        self.count_spin.setValue(8)
        form.addRow("Sub-Items Count:", self.count_spin)
        
        layout.addLayout(form)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.generate_objects)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def generate_objects(self):
        idx_str = self.idx_input.text().strip().upper()
        if not idx_str or not all(c in "0123456789ABCDEF" for c in idx_str):
            QMessageBox.warning(self, "Error", "Invalid Hex Index.")
            return
            
        if self.parser.has_section(idx_str):
            QMessageBox.warning(self, "Error", "Index already exists!")
            return
            
        # Create Main Index
        self.parser.add_section(idx_str)
        self.parser.set(idx_str, "ParameterName", self.name_input.text())
        self.parser.set(idx_str, "ObjectType", "0x8" if self.type_combo.currentIndex() == 0 else "0x9")
        self.parser.set(idx_str, "SubNumber", str(self.count_spin.value() + 1))
        
        # Create sub0
        sub0 = f"{idx_str}sub0"
        self.parser.add_section(sub0)
        self.parser.set(sub0, "ParameterName", "Highest sub-index supported")
        self.parser.set(sub0, "ObjectType", "0x7")
        self.parser.set(sub0, "DataType", "0x0005")
        self.parser.set(sub0, "AccessType", "ro")
        self.parser.set(sub0, "DefaultValue", str(self.count_spin.value()))
        self.parser.set(sub0, "PDOMapping", "0")
        
        # Create subN
        dt_val = self.dt_combo.currentText().split(" ")[0]
        for i in range(1, self.count_spin.value() + 1):
            subN = f"{idx_str}sub{i}"
            self.parser.add_section(subN)
            self.parser.set(subN, "ParameterName", f"Sub-item {i}")
            self.parser.set(subN, "ObjectType", "0x7")
            self.parser.set(subN, "DataType", dt_val)
            self.parser.set(subN, "AccessType", "rw")
            self.parser.set(subN, "DefaultValue", "0")
            self.parser.set(subN, "PDOMapping", "1")
            
        self.accept()
