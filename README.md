# PyCANopen EDS Editor

A modern, cross-platform CANopen Electronic Data Sheet (EDS) editor built with Python and PySide6.

## Features
- **Dynamic Profile Injection**: Automatically load CANopen standard profiles (301, 401, 402, 406, 442) from JSON templates.
- **Dedicated Device Info Forms**: User-friendly UI for editing LSS, Baud Rates, and Device metadata.
- **Visual PDO Mapper**: Drag-and-drop interface for configuring Transmit and Receive PDO memory layouts safely.
- **EDS Validation & Linter**: Ensures your EDS is strictly compliant with the CANopen standard.
- **C-Header Export**: Automatically generates `OD.h` and `OD.c` files with standard structs and routing tables, ready to be dropped into embedded firmware stacks like CANopenNode.
- **Smart Object Wizard**: Instantly scaffold complex Arrays and Records with multiple sub-indices in a single click.
- **HTML Report Generation**: Exports your entire Object Dictionary and visual PDO memory maps into a clean, printable HTML document.

## License
This software is licensed under the GPLv3 License.
Copyright (C) 2026 Diego Asanza
