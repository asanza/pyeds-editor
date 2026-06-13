import configparser
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QTreeWidget, QTreeWidgetItem, QLabel, QPushButton, QGroupBox, QSplitter,
    QMessageBox, QComboBox, QWidget
)
from PySide6.QtCore import Qt, QMimeData, QByteArray
from PySide6.QtGui import QDrag

class DraggableListWidget(QListWidget):
    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setSelectionMode(QListWidget.SingleSelection)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item: return
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # We store: index:subindex:bitlength
        data = item.data(Qt.UserRole)
        mime_data.setText(data)
        
        drag.setMimeData(mime_data)
        drag.exec_(supportedActions)

class DroppableTreeWidget(QTreeWidget):
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setColumnCount(3)
        self.setHeaderLabels(["PDO Slot / Mapped Object", "Hex Value", "Bit Length"])
        self.header().resizeSection(0, 250)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        text = event.mimeData().text()
        if not text: return
        
        target_item = self.itemAt(event.pos())
        if not target_item:
            return
            
        # Is it a PDO parent node? (TopLevelItem)
        if target_item.parent() is None:
            pdo_parent = target_item
        else:
            pdo_parent = target_item.parent()
            
        # Check current total length
        current_bits = 0
        for i in range(pdo_parent.childCount()):
            child = pdo_parent.child(i)
            current_bits += int(child.text(2))
            
        # parse incoming data
        idx, sub, length, name = text.split(":", 3)
        length_int = int(length)
        
        if current_bits + length_int > 64:
            QMessageBox.warning(self, "PDO Size Error", f"Cannot map this object. Exceeds 64 bits limit (Currently {current_bits} bits).")
            return
            
        hex_val = f"0x{int(idx, 16):04X}{int(sub, 16):02X}{length_int:02X}"
        
        new_item = QTreeWidgetItem(pdo_parent, [f"[{idx}sub{sub}] {name}", hex_val, str(length_int)])
        new_item.setData(0, Qt.UserRole, "mapping")
        pdo_parent.setExpanded(True)
        
        event.acceptProposedAction()

class PDOMapperDialog(QDialog):
    def __init__(self, parser, parent=None):
        super().__init__(parent)
        self.parser = parser
        self.setWindowTitle("Visual PDO Mapper")
        self.resize(900, 600)
        
        layout = QVBoxLayout(self)
        
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        
        # Left side: Variables
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("Mappable Objects (Drag these)"))
        
        self.var_list = DraggableListWidget()
        left_layout.addWidget(self.var_list)
        splitter.addWidget(left_widget)
        
        # Right side: PDOs
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(QLabel("View:"))
        self.pdo_type_combo = QComboBox()
        self.pdo_type_combo.addItems(["Transmit PDOs (TPDO)", "Receive PDOs (RPDO)"])
        self.pdo_type_combo.currentIndexChanged.connect(self.populate_pdos)
        controls_layout.addWidget(self.pdo_type_combo)
        
        btn_add_pdo = QPushButton("Add PDO")
        btn_add_pdo.clicked.connect(self.add_pdo)
        controls_layout.addWidget(btn_add_pdo)
        right_layout.addLayout(controls_layout)
        
        self.pdo_tree = DroppableTreeWidget()
        right_layout.addWidget(self.pdo_tree)
        
        btn_delete_mapping = QPushButton("Remove Selected Mapping")
        btn_delete_mapping.clicked.connect(self.remove_mapping)
        right_layout.addWidget(btn_delete_mapping)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([300, 600])
        
        # Bottom controls
        bottom_layout = QHBoxLayout()
        btn_save = QPushButton("Save Mappings to EDS")
        btn_save.clicked.connect(self.save_mappings)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        
        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_cancel)
        bottom_layout.addWidget(btn_save)
        layout.addLayout(bottom_layout)
        
        self.populate_variables()
        self.populate_pdos()

    def get_bit_length(self, datatype):
        mapping = {
            "0x0001": 1, "0x0002": 8, "0x0003": 16, "0x0004": 32,
            "0x0005": 8, "0x0006": 16, "0x0007": 32, "0x0008": 32,
            "0x0020": 64, "0x0021": 64
        }
        dt = datatype.lower()
        if dt.startswith("0x") and len(dt) < 6: dt = "0x" + dt[2:].zfill(4)
        return mapping.get(dt, 0)

    def populate_variables(self):
        self.var_list.clear()
        
        for sec in sorted(self.parser.sections()):
            if "sub" in sec.lower():
                parent = sec.lower().split("sub")[0]
                obj_type = self.parser.get(parent, "ObjectType", fallback="0x7").lower()
                if obj_type not in ["0x8", "0x08", "0x9", "0x09"]:
                    continue
                
                dt = self.parser.get(sec, "DataType", fallback="")
                bits = self.get_bit_length(dt)
                if bits > 0:
                    name = self.parser.get(sec, "ParameterName", fallback="Unnamed")
                    idx = parent.zfill(4).upper()
                    sub = sec.lower().split("sub")[1].zfill(2).upper()
                    
                    item = QListWidgetItem(f"[{idx}sub{sub}] {name} ({bits} bits)")
                    item.setData(Qt.UserRole, f"{idx}:{sub}:{bits}:{name}")
                    self.var_list.addItem(item)
                    
            elif sec.isdigit() and len(sec) == 4:
                obj_type = self.parser.get(sec, "ObjectType", fallback="0x7").lower()
                if obj_type in ["0x7", "0x07"]:
                    dt = self.parser.get(sec, "DataType", fallback="")
                    bits = self.get_bit_length(dt)
                    if bits > 0:
                        name = self.parser.get(sec, "ParameterName", fallback="Unnamed")
                        idx = sec.zfill(4).upper()
                        sub = "00"
                        item = QListWidgetItem(f"[{idx}] {name} ({bits} bits)")
                        item.setData(Qt.UserRole, f"{idx}:{sub}:{bits}:{name}")
                        self.var_list.addItem(item)

    def populate_pdos(self):
        self.pdo_tree.clear()
        is_tx = self.pdo_type_combo.currentIndex() == 0
        base_map_idx = 0x1A00 if is_tx else 0x1600
        pdo_name = "TPDO" if is_tx else "RPDO"
        
        for i in range(32):
            map_idx = f"{base_map_idx + i:04X}"
            
            if self.parser.has_section(map_idx):
                parent_item = QTreeWidgetItem(self.pdo_tree, [f"{pdo_name} {i+1} (0x{map_idx})", "", ""])
                parent_item.setData(0, Qt.UserRole, map_idx)
                
                sub_count_str = self.parser.get(map_idx, "SubNumber", fallback="0")
                try: sub_count = int(sub_count_str)
                except: sub_count = 0
                
                for s in range(1, sub_count + 1):
                    sub_sec = f"{map_idx}sub{s}"
                    if self.parser.has_section(sub_sec):
                        default_val = self.parser.get(sub_sec, "DefaultValue", fallback="0x00000000")
                        try:
                            val_int = int(default_val, 16)
                            length = val_int & 0xFF
                            sub_idx = (val_int >> 8) & 0xFF
                            obj_idx = (val_int >> 16) & 0xFFFF
                            target_name = "Unknown Object"
                            target_sec = f"{obj_idx:04X}sub{sub_idx:02X}"
                            if self.parser.has_section(target_sec):
                                target_name = self.parser.get(target_sec, "ParameterName", fallback="Unknown Object")
                            elif self.parser.has_section(target_sec.upper()):
                                target_name = self.parser.get(target_sec.upper(), "ParameterName", fallback="Unknown Object")
                            elif self.parser.has_section(target_sec.lower()):
                                target_name = self.parser.get(target_sec.lower(), "ParameterName", fallback="Unknown Object")
                            else:
                                target_sec_no_sub = f"{obj_idx:04X}"
                                if self.parser.has_section(target_sec_no_sub):
                                    target_name = self.parser.get(target_sec_no_sub, "ParameterName", fallback="Unknown Object")
                                    
                            child = QTreeWidgetItem(parent_item, [f"[{obj_idx:04X}sub{sub_idx:02X}] {target_name}", f"0x{val_int:08X}", str(length)])
                            child.setData(0, Qt.UserRole, "mapping")
                        except ValueError:
                            pass
                parent_item.setExpanded(True)

    def add_pdo(self):
        is_tx = self.pdo_type_combo.currentIndex() == 0
        base_map_idx = 0x1A00 if is_tx else 0x1600
        pdo_name = "TPDO" if is_tx else "RPDO"
        
        for i in range(32):
            map_idx = f"{base_map_idx + i:04X}"
            if not self.parser.has_section(map_idx):
                parent_item = QTreeWidgetItem(self.pdo_tree, [f"{pdo_name} {i+1} (0x{map_idx})", "", ""])
                parent_item.setData(0, Qt.UserRole, map_idx)
                parent_item.setExpanded(True)
                return
        QMessageBox.warning(self, "Error", "No free PDO slots found.")

    def remove_mapping(self):
        item = self.pdo_tree.currentItem()
        if not item: return
        if item.data(0, Qt.UserRole) == "mapping":
            item.parent().removeChild(item)
        else:
            root = self.pdo_tree.invisibleRootItem()
            root.removeChild(item)

    def save_mappings(self):
        root = self.pdo_tree.invisibleRootItem()
        for i in range(root.childCount()):
            pdo_node = root.child(i)
            map_idx = pdo_node.data(0, Qt.UserRole)
            
            if not self.parser.has_section(map_idx):
                self.parser.add_section(map_idx)
                self.parser.set(map_idx, "ParameterName", f"PDO Mapping {map_idx}")
                self.parser.set(map_idx, "ObjectType", "0x8")
                
            sub_count_str = self.parser.get(map_idx, "SubNumber", fallback="0")
            try: old_count = int(sub_count_str)
            except: old_count = 0
            for s in range(1, old_count + 1):
                if self.parser.has_section(f"{map_idx}sub{s}"):
                    self.parser.remove_section(f"{map_idx}sub{s}")
                    
            if not self.parser.has_section(f"{map_idx}sub0"):
                self.parser.add_section(f"{map_idx}sub0")
                
            self.parser.set(f"{map_idx}sub0", "ParameterName", "Number of mapped objects")
            self.parser.set(f"{map_idx}sub0", "ObjectType", "0x7")
            self.parser.set(f"{map_idx}sub0", "DataType", "0x0005")
            self.parser.set(f"{map_idx}sub0", "AccessType", "rw")
            self.parser.set(f"{map_idx}sub0", "DefaultValue", str(pdo_node.childCount()))
            self.parser.set(map_idx, "SubNumber", str(pdo_node.childCount() + 1))
            
            for s in range(pdo_node.childCount()):
                child = pdo_node.child(s)
                hex_val = child.text(1)
                
                sub_sec = f"{map_idx}sub{s+1}"
                if not self.parser.has_section(sub_sec):
                    self.parser.add_section(sub_sec)
                    
                self.parser.set(sub_sec, "ParameterName", f"Mapped object {s+1}")
                self.parser.set(sub_sec, "ObjectType", "0x7")
                self.parser.set(sub_sec, "DataType", "0x0007")
                self.parser.set(sub_sec, "AccessType", "rw")
                self.parser.set(sub_sec, "DefaultValue", hex_val)
                self.parser.set(sub_sec, "PDOMapping", "0")
                
        QMessageBox.information(self, "Success", "PDO Mappings applied to current session.")
        self.accept()
