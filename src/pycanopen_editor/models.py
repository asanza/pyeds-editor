import os
import json
import configparser
import xml.etree.ElementTree as ET
import re

class EDSParser(configparser.ConfigParser):
    def __init__(self, *args, **kwargs):
        kwargs['interpolation'] = None
        super().__init__(*args, **kwargs)

    # Override optionxform to preserve the case of keys
    def optionxform(self, optionstr):
        return optionstr

class DeviceModel:
    def load(self, filepath: str) -> None:
        raise NotImplementedError

    def save(self, filepath: str) -> None:
        raise NotImplementedError

    def has_section(self, section: str) -> bool:
        raise NotImplementedError

    def sections(self) -> list:
        raise NotImplementedError

    def get(self, section: str, key: str, fallback=None) -> str:
        raise NotImplementedError

    def set(self, section: str, key: str, value: str) -> None:
        raise NotImplementedError

    def add_section(self, section: str) -> None:
        raise NotImplementedError

    def remove_section(self, section: str) -> None:
        raise NotImplementedError

    def items(self, section: str) -> list:
        raise NotImplementedError

    def get_metadata(self, section: str) -> str:
        raise NotImplementedError

    def set_metadata(self, section: str, text: str) -> None:
        raise NotImplementedError

    def is_canopen_fd(self) -> bool:
        raise NotImplementedError


class EDSModel(DeviceModel):
    def __init__(self):
        self.parser = EDSParser()
        self.meta_data = {}

    def load(self, filepath: str) -> None:
        self.parser.clear()
        self.parser.read(filepath)
        
        meta_file = filepath + ".meta.json"
        self.meta_data = {}
        if os.path.exists(meta_file):
            try:
                with open(meta_file, 'r') as f:
                    meta = json.load(f)
                    if "descriptions" in meta:
                        self.meta_data = meta["descriptions"]
            except Exception:
                pass

    def save(self, filepath: str) -> None:
        with open(filepath, "w") as f:
            self.parser.write(f)
            
        meta_file = filepath + ".meta.json"
        if self.meta_data:
            with open(meta_file, 'w') as f:
                json.dump({"descriptions": self.meta_data}, f, indent=4)
        elif os.path.exists(meta_file):
            try:
                os.remove(meta_file)
            except OSError:
                pass

    def has_section(self, section: str) -> bool:
        return self.parser.has_section(section)

    def sections(self) -> list:
        return self.parser.sections()

    def get(self, section: str, key: str, fallback=None) -> str:
        return self.parser.get(section, key, fallback=fallback)

    def set(self, section: str, key: str, value: str) -> None:
        if not self.parser.has_section(section):
            self.parser.add_section(section)
        self.parser.set(section, key, value)

    def add_section(self, section: str) -> None:
        if not self.parser.has_section(section):
            self.parser.add_section(section)

    def remove_section(self, section: str) -> None:
        if self.parser.has_section(section):
            self.parser.remove_section(section)
        if section in self.meta_data:
            del self.meta_data[section]

    def items(self, section: str) -> list:
        if self.parser.has_section(section):
            return self.parser.items(section)
        return []

    def get_metadata(self, section: str) -> str:
        return self.meta_data.get(section, "")

    def set_metadata(self, section: str, text: str) -> None:
        if text.strip():
            self.meta_data[section] = text.strip()
        elif section in self.meta_data:
            del self.meta_data[section]

    def is_canopen_fd(self) -> bool:
        return False


class XDDModel(DeviceModel):
    def __init__(self):
        # We start with a base ISO15745 profile structure.
        self.root = ET.Element("ISO15745Profile")
        self.profile_body = ET.SubElement(self.root, "ProfileBody")
        self.app_process = ET.SubElement(self.profile_body, "ApplicationProcess")
        self.obj_list = ET.SubElement(self.app_process, "CANopenObjectList")
        
        # Dictionary to quickly map section string to XML Element for standard lookup
        self._section_map = {}
        
        # Store device info/file info fields
        self.device_info = {}
        self.file_info = {}
        self.ns = ""

    def _find_all(self, elem, tag_name):
        return [e for e in elem if e.tag.endswith(tag_name)]

    def _find_first(self, elem, tag_name):
        for e in elem.iter():
            if e.tag.endswith(tag_name):
                return e
        return None

    def _build_section_map(self):
        self._section_map = {}
        for obj in self._find_all(self.obj_list, "CANopenObject"):
            idx = obj.get("index", "")
            if not idx:
                continue
            idx_hex = f"{int(idx, 16):04X}"
            self._section_map[idx_hex] = obj
            
            for sub in self._find_all(obj, "CANopenSubObject"):
                sub_idx = sub.get("subIndex", "")
                if not sub_idx:
                    continue
                sub_hex = f"{int(sub_idx, 16):X}"
                self._section_map[f"{idx_hex}SUB{sub_hex}"] = sub

    def load(self, filepath: str) -> None:
        # Register namespaces to preserve them on save
        for event, (ns_prefix, ns_uri) in ET.iterparse(filepath, events=['start-ns']):
            ET.register_namespace(ns_prefix, ns_uri)
            
        tree = ET.parse(filepath)
        self.root = tree.getroot()
        
        # Determine default namespace prefix for creating new elements
        self.ns = ""
        m = re.match(r'\{.*\}', self.root.tag)
        if m:
            self.ns = m.group(0)
            
        # Find CANopenObjectList
        self.obj_list = self._find_first(self.root, "CANopenObjectList")
        if self.obj_list is None:
            # Recreate if missing
            self.profile_body = self._find_first(self.root, "ProfileBody")
            if self.profile_body is None:
                self.profile_body = ET.SubElement(self.root, f"{self.ns}ProfileBody")
            self.app_process = self._find_first(self.profile_body, "ApplicationProcess")
            if self.app_process is None:
                self.app_process = ET.SubElement(self.profile_body, f"{self.ns}ApplicationProcess")
            self.obj_list = ET.SubElement(self.app_process, f"{self.ns}CANopenObjectList")
            
        self._build_section_map()
        
        # Load DeviceInfo/FileInfo from custom extensions or standard headers if available
        # For simplicity, we just clear and rely on XDD attributes
        self.device_info = {}
        self.file_info = {}

    def save(self, filepath: str) -> None:
        tree = ET.ElementTree(self.root)
        ET.indent(tree, space="  ", level=0)
        tree.write(filepath, encoding="utf-8", xml_declaration=True)

    def _get_element_for_section(self, section: str):
        if section in ["DeviceInfo", "FileInfo", "Comments", "DummyUsage"]:
            return None
        return self._section_map.get(section.upper())

    def has_section(self, section: str) -> bool:
        if section == "DeviceInfo" and self.device_info:
            return True
        if section == "FileInfo" and self.file_info:
            return True
        return self._get_element_for_section(section) is not None

    def sections(self) -> list:
        secs = []
        if self.device_info: secs.append("DeviceInfo")
        if self.file_info: secs.append("FileInfo")
        secs.extend(list(self._section_map.keys()))
        return secs

    def get(self, section: str, key: str, fallback=None) -> str:
        if section == "DeviceInfo":
            return self.device_info.get(key, fallback)
        if section == "FileInfo":
            return self.file_info.get(key, fallback)
            
        elem = self._get_element_for_section(section)
        if elem is None:
            return fallback
            
        # Map EDS keys to XDD attributes/elements
        if key == "ParameterName":
            name = elem.get("name")
            if name is not None: return name
        elif key == "ObjectType":
            ot = elem.get("objectType")
            ot_map = {"VAR": "7", "ARRAY": "8", "RECORD": "9"}
            if ot is not None: return f"0x{ot_map.get(ot, ot)}"
        elif key == "DataType":
            dt_node = self._find_first(elem, "datatype")
            if dt_node is not None and len(dt_node) > 0:
                type_tag = dt_node[0].tag.split('}')[-1]
                dt_map = {"BOOLEAN": "0x0001", "INTEGER8": "0x0002", "INTEGER16": "0x0003", "INTEGER32": "0x0004", "UNSIGNED8": "0x0005", "UNSIGNED16": "0x0006", "UNSIGNED32": "0x0007", "REAL32": "0x0008", "VISIBLE_STRING": "0x0009"}
                return dt_map.get(type_tag, f"0x{type_tag}")
        elif key == "AccessType":
            acc = self._find_first(elem, "access")
            if acc is not None: return acc.get("value")
        elif key == "DefaultValue":
            dv = self._find_first(elem, "defaultValue")
            if dv is not None: return dv.get("value")
        elif key == "SubNumber":
            sub_objs = self._find_all(elem, "CANopenSubObject")
            return str(len(sub_objs))
            
        return fallback

    def set(self, section: str, key: str, value: str) -> None:
        if section == "DeviceInfo":
            self.device_info[key] = value
            return
        if section == "FileInfo":
            self.file_info[key] = value
            return
            
        self.add_section(section)
        elem = self._get_element_for_section(section)
        if elem is None: return
        
        if key == "ParameterName":
            elem.set("name", value)
        elif key == "ObjectType":
            if value.startswith("0x"): value = value[2:]
            ot_map = {"7": "VAR", "8": "ARRAY", "9": "RECORD"}
            elem.set("objectType", ot_map.get(value, value))
        elif key == "DataType":
            if value.startswith("0x"): value = value[2:]
            dt_map = {"0001": "BOOLEAN", "0002": "INTEGER8", "0003": "INTEGER16", "0004": "INTEGER32", "0005": "UNSIGNED8", "0006": "UNSIGNED16", "0007": "UNSIGNED32", "0008": "REAL32", "0009": "VISIBLE_STRING"}
            val_str = dt_map.get(value, value)
            dt_node = self._find_first(elem, "datatype")
            if dt_node is None:
                dt_node = ET.SubElement(elem, f"{self.ns}datatype")
            for child in list(dt_node):
                dt_node.remove(child)
            ET.SubElement(dt_node, f"{self.ns}{val_str}")
        elif key == "AccessType":
            acc = self._find_first(elem, "access")
            if acc is None:
                acc = ET.SubElement(elem, f"{self.ns}access")
            acc.set("value", value)
        elif key == "DefaultValue":
            dv = self._find_first(elem, "defaultValue")
            if dv is None:
                dv = ET.SubElement(elem, f"{self.ns}defaultValue")
            dv.set("value", value)

    def add_section(self, section: str) -> None:
        if self.has_section(section):
            return
            
        section = section.upper()
        if "SUB" in section:
            idx, sub = section.split("SUB")
            parent_elem = self._section_map.get(idx)
            if parent_elem is None:
                self.add_section(idx)
                parent_elem = self._section_map.get(idx)
            
            sub_elem = ET.SubElement(parent_elem, f"{self.ns}CANopenSubObject")
            sub_elem.set("subIndex", f"{int(sub, 16):02X}")
            self._section_map[section] = sub_elem
        else:
            obj_elem = ET.SubElement(self.obj_list, f"{self.ns}CANopenObject")
            obj_elem.set("index", section)
            self._section_map[section] = obj_elem

    def remove_section(self, section: str) -> None:
        section = section.upper()
        elem = self._get_element_for_section(section)
        if elem is not None:
            if "SUB" in section:
                idx = section.split("SUB")[0]
                parent = self._get_element_for_section(idx)
                if parent is not None:
                    parent.remove(elem)
            else:
                self.obj_list.remove(elem)
            del self._section_map[section]

    def items(self, section: str) -> list:
        keys = ["ParameterName", "ObjectType", "DataType", "AccessType", "DefaultValue"]
        if "SUB" not in section.upper() and section not in ["DeviceInfo", "FileInfo"]:
            keys.append("SubNumber")
            
        res = []
        for k in keys:
            v = self.get(section, k)
            if v is not None:
                res.append((k, v))
        return res

    def get_metadata(self, section: str) -> str:
        elem = self._get_element_for_section(section)
        if elem is not None:
            desc = self._find_first(elem, "comment")
            if desc is not None and desc.text is not None:
                return desc.text
        return ""

    def set_metadata(self, section: str, text: str) -> None:
        elem = self._get_element_for_section(section)
        if elem is not None:
            desc = self._find_first(elem, "comment")
            if text.strip():
                if desc is None:
                    desc = ET.SubElement(elem, f"{self.ns}comment")
                    desc.set("lang", "en")
                desc.text = text.strip()
            else:
                if desc is not None:
                    elem.remove(desc)

    def is_canopen_fd(self) -> bool:
        return True
