import sys
import os
import copy
import configparser
import logging
from pathlib import Path
from lxml import etree as ET
import subprocess # <-- ADDED IMPORT
import sys  

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QSplitter, QTabWidget, QListWidget, QListWidgetItem, QLineEdit,
    QPushButton, QLabel, QScrollArea, QSizePolicy, QSpacerItem, QGridLayout,
    QFileDialog, QMessageBox, QInputDialog, QCompleter, QMenuBar, QStatusBar, QDialog, QMenu 
)
from PySide6.QtCore import QMargins, Qt, QStringListModel, Signal, QPoint 
from PySide6.QtGui import QAction, QPalette, QColor, QShortcut, QKeySequence, QIcon

# --- Constants ---
TAG_ABILITIES = "abilities"
TAG_ITEMS = "items"
TAG_ABILITY = "ability"
TAG_ITEM = "item"
TAG_TAGS = "tags"
TAG_BASE_ABILITIES = "base_abilities"
TAG_RECYCLING_PARTS = "recycling_parts"
TAG_VARIANTS = "variants"
TAG_VARIANT = "variant"
TAG_PARTS = "parts" # Child of recycling_parts
TAG_ABILITY_REF = "a" # Child of base_abilities

# --- Logging Setup ---
# Basic configuration - logs to console
# You can customize this to log to a file, set different levels, etc.
logging.basicConfig(level=logging.DEBUG, # Change to logging.INFO for less verbose output
                    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

# --- Custom Widget for Generic Properties (like in Abilities) ---
class PropertyWidget(QWidget):
    # Assuming PropertyWidget doesn't need major changes based on the initial analysis
    # Keep its internal logic as it was, but ensure consistency
    def __init__(self, element, file_path, editor_instance, parent=None):
        super().__init__(parent)
        self.element = element
        self.file_path = file_path
        self.editor = editor_instance
        self._local_populating = False # Use a local flag if needed

        # --- MAIN HORIZONTAL LAYOUT FOR THE ENTIRE ROW ---
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0) # Remove outer margins

        # --- 1. Property Name Label ---
        self.name_label = QLabel(f"{element.tag}:")
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.name_label.setFixedWidth(160) # Fixed width for alignment
        self.main_layout.addWidget(self.name_label)

        # --- 2. Container and Layout for Attributes ---
        self.attributes_container = QWidget()
        self.attributes_layout = QHBoxLayout(self.attributes_container) # Layout *only* for attributes
        self.attributes_layout.setContentsMargins(5, 0, 5, 0) # Small inner margin
        self.attributes_layout.setAlignment(Qt.AlignmentFlag.AlignLeft) # Keep attributes close on the left
        self.main_layout.addWidget(self.attributes_container) # Add container to main layout

        self.attribute_widgets = {} # Dictionary to store QLineEdit widgets

        # Add widgets for existing attributes
        for key, value in sorted(element.attrib.items()):
            self._add_attribute_widgets_to_layout(key, value)

        # --- 3. Stretchable Spacer BEFORE buttons ---
        self.main_layout.addStretch(1)

        # --- 4. "+Attr" Button ---
        self.add_attr_button = QPushButton("+Attr")
        self.add_attr_button.setFixedWidth(50)
        self.add_attr_button.setToolTip("Add a new attribute to this property")
        self.add_attr_button.clicked.connect(self.add_attribute)
        self.main_layout.addWidget(self.add_attr_button)

        # --- 5. "X" Button (Remove Property) ---
        self.remove_button = QPushButton("X")
        self.remove_button.setFixedWidth(30)
        self.remove_button.setToolTip(f"Remove the entire property '{element.tag}'")
        self.remove_button.clicked.connect(self.remove_self)
        self.main_layout.addWidget(self.remove_button)

    def _add_attribute_widgets_to_layout(self, key, value):
        """Helper to add label and input for an attribute to the layout."""
        self._local_populating = True
        try:
            logging.debug(f"PropertyWidget: Adding attribute widgets for '{key}' = '{value}' in <{self.element.tag}>")
            attr_label = QLabel(f"{key}:")
            attr_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            attr_input = QLineEdit(value)
            attr_input.setObjectName(f"prop_input_{self.element.tag}_{key}") # Unique object name

            # Add widgets to the *attributes* layout FIRST
            self.attributes_layout.addWidget(attr_label)
            self.attributes_layout.addWidget(attr_input)
            self.attribute_widgets[key] = attr_input # Track the widget

            # Attach QCompleter AFTER adding to layout
            # Use a consistent pattern like the main editor's _attach_completer
            if key == 'type':
                 self.editor._attach_completer(attr_input, self.editor.property_attr_type_model, "Property Type")
            elif key == 'always_random':
                 self.editor._attach_completer(attr_input, self.editor.boolean_value_model, "Property Always Random")
            # Add other elif for specific attributes if needed

            # Connect signal
            attr_input.editingFinished.connect(lambda k=key, i=attr_input: self.attribute_changed(k, i.text()))
        finally:
            self._local_populating = False

    def attribute_changed(self, key, new_value):
        if self.editor._populating_details or self._local_populating: return # Check both flags
        old_value = self.element.get(key)
        if old_value != new_value:
            logging.info(f"Property Attr '{key}' changed from '{old_value}' to '{new_value}' for <{self.element.tag}> in file {os.path.basename(self.file_path)}")
            self.element.set(key, new_value)
            self.editor.mark_file_modified(self.file_path)

    def add_attribute(self):
        """Adds a new attribute to this specific property (element)."""
        if self.editor._populating_details or self._local_populating: return

        dialog = QInputDialog(self.editor)
        dialog.setWindowTitle("Add Property Attribute")
        dialog.setLabelText("Name of new attribute:")
        line_edit = dialog.findChild(QLineEdit)
        if line_edit:
            # Attach model with known property attribute names
            self.editor._attach_completer(line_edit, self.editor.property_attribute_name_model, "New Property Attribute Name")

        if dialog.exec() == QDialog.DialogCode.Accepted:
            attr_name = dialog.textValue().strip().replace(" ", "_") # Basic cleanup
            if attr_name and attr_name not in self.element.attrib:
                default_value = "" # Can set a default like "0" or "false"
                logging.info(f"Adding attribute '{attr_name}' to <{self.element.tag}> with default value '{default_value}'")
                self.element.set(attr_name, default_value)
                self.editor.mark_file_modified(self.file_path)

                # Dynamically add widgets to the UI
                self._add_attribute_widgets_to_layout(attr_name, default_value)

                # Update the editor's global set and model for property attribute names
                if attr_name not in self.editor.all_property_attribute_names:
                    self.editor.all_property_attribute_names.add(attr_name)
                    self.editor._update_single_completer_model(
                        self.editor.property_attribute_name_model,
                        self.editor.all_property_attribute_names,
                        "property_attribute_name"
                    )

            elif attr_name in self.element.attrib:
                QMessageBox.warning(self, "Error", f"Attribute '{attr_name}' already exists for this property.")
            elif not attr_name:
                 QMessageBox.warning(self, "Error", "Attribute name cannot be empty.")

    def remove_self(self):
        """Removes this entire property (PropertyWidget) and its corresponding XML element."""
        if self.editor._populating_details or self._local_populating: return

        confirm = QMessageBox.question(self, "Remove Property", f"Are you sure you want to remove the entire property '{self.element.tag}'?")
        if confirm == QMessageBox.StandardButton.Yes:
            # Find parent element using the editor's helper
            parent_element = self.editor.get_parent_element(self.element, self.file_path)
            if parent_element is not None:
                try:
                    logging.info(f"Removing property element <{self.element.tag}> from parent <{parent_element.tag}> in file {os.path.basename(self.file_path)}")
                    parent_element.remove(self.element)
                    self.editor.mark_file_modified(self.file_path)
                    # Deleting the widget will remove it from the layout
                    self.deleteLater()
                    logging.info(f"Removed property widget and element: {self.element.tag}")
                    # Note: Not refreshing the whole panel to avoid recreating everything.
                    # Could emit a signal if other UI parts need to react.
                except ValueError:
                    logging.error(f"Element {self.element.tag} not found in parent during remove_self.", exc_info=True)
                    self.deleteLater() # Still remove widget even on XML error
                except Exception as e:
                    logging.error(f"Error removing property widget/element: {e}", exc_info=True)
                    self.deleteLater()
            else:
                logging.error(f"Could not find parent element for <{self.element.tag}> to remove.")
                self.deleteLater() # Remove widget even if XML parent not found


class WitcherXMLEditor(QMainWindow):

    # Define sets for known child tags to differentiate properties from structure
    KNOWN_ITEM_CHILD_TAGS = {TAG_TAGS, TAG_BASE_ABILITIES, TAG_RECYCLING_PARTS, TAG_VARIANTS}
    KNOWN_ABILITY_CHILD_TAGS = {TAG_TAGS} # Example, adjust if abilities have other standard sections

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Witcher 3 XML Editor v1.0")
        self._setup_icon()

        self.setGeometry(100, 100, 1200, 800)

        # --- Configuration Path ---
        if getattr(sys, 'frozen', False): # Check if running as bundled executable
            self.base_path = Path(sys.executable).parent
        else:
            self.base_path = Path(__file__).parent
        self.config_file = self.base_path / "editor_config.ini"
        self.last_folder = ""
        logging.info(f"Base path: {self.base_path}, Config file: {self.config_file}")

        # --- Data Storage ---
        self.loaded_files = {}      # {filepath: {'tree': ET.ElementTree, 'root': ET.Element}}
        self.abilities_map = {}     # {ability_name: {'filepath': str, 'element': ET.Element}}
        self.items_map = {}         # {item_name: {'filepath': str, 'element': ET.Element}}
        self.modified_files = set() # {filepath}

        # --- Autocompletion Data Sets ---
        self.all_property_names = set()
        self.all_item_attribute_names = set()
        self.all_variant_attribute_names = set()
        self.all_property_attribute_names = set()
        self.all_tags = set()
        self.all_ability_names = set()
        self.all_item_names = set()
        self.all_recycling_part_names = set()
        self.all_item_categories = set()
        self.all_ability_modes = set()
        self.all_variant_nested_tags = set()
        self.all_equip_templates = set()
        self.all_loc_keys = set()
        self.all_icon_paths = set()
        self.all_prop_attr_types = set()
        self.all_equip_slots = set()
        self.all_hold_slots = set()
        self.all_hands = set()
        self.all_sound_ids = set()
        self.all_events = set()
        self.all_anim_actions = set() # Combined for draw/holster act/deact

        # --- Menu Action References ---
        self.open_action = None
        self.save_action = None
        self.save_all_action = None
        self.save_as_action = None
        # self.exit_action = None # Usually handled by window close
        self.author_action = None

        # --- Application State ---
        self.current_selection_name = None      # Name of selected item/ability
        self.current_selection_type = None      # 'ability' or 'item'
        self.current_selection_element = None   # lxml element of selection
        self.current_selection_filepath = None  # File path of selection
        self._populating_details = False        # Flag to prevent signals during UI updates

        # --- Autocompletion Models ---
        self.item_attribute_name_model = QStringListModel(self)
        self.variant_attribute_name_model = QStringListModel(self)
        self.property_attribute_name_model = QStringListModel(self)
        self.ability_name_model = QStringListModel(self)
        self.item_name_model = QStringListModel(self)
        self.recycling_part_name_model = QStringListModel(self)
        self.item_category_model = QStringListModel(self)
        self.ability_mode_model = QStringListModel(self)
        self.variant_nested_tag_model = QStringListModel(self)
        self.tag_model = QStringListModel(self)
        self.property_name_model = QStringListModel(self) # Generic property tags
        self.equip_template_model = QStringListModel(self)
        self.localisation_key_model = QStringListModel(self)
        self.icon_path_model = QStringListModel(self)
        self.property_attr_type_model = QStringListModel(self)
        self.equip_slot_model = QStringListModel(self)
        self.boolean_value_model = QStringListModel(["true", "false"], self) # Static
        self.hold_slot_model = QStringListModel(self)
        self.hand_model = QStringListModel(self)
        self.sound_id_model = QStringListModel(self)
        self.event_model = QStringListModel(self)
        self.anim_action_model = QStringListModel(self) # Combined model
        self.enhancement_slots_model = QStringListModel(["0", "1", "2", "3"], self) # Static

        # --- Initialize UI and Connect Signals ---
        self._init_ui()
        self._connect_signals()
        self._connect_context_menu_signals() # <-- ADDED: Connect context menu signals separately
        self._setup_shortcuts() # Setup keyboard shortcuts

        # --- Status Bar ---
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready.")
        self.author_label = QLabel("Gerwant 2025") # Keep author credit
        self.statusBar.addPermanentWidget(self.author_label)

        # --- Load Config and Attempt Startup Load ---
        self.load_config()
        if self.last_folder and Path(self.last_folder).is_dir():
            logging.info(f"Last used folder found in config: {self.last_folder}")
            self.load_folder_on_startup(self.last_folder)
        else:
            logging.warning("No saved folder in config or folder does not exist. Use 'File -> Open Folder...'.")
            self.statusBar.showMessage("Ready. Open a folder containing XML files.")

    def _setup_icon(self):
        """Sets the window icon."""
        # Determine base path correctly for frozen/unfrozen state
        base_path = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
        icon_path = base_path / "editor_icon.ico"
        logging.info(f"Looking for icon at: {icon_path}")
        if icon_path.exists():
            try:
                icon = QIcon(str(icon_path))
                self.setWindowIcon(icon)
                QApplication.setWindowIcon(icon) # Also set for the application context
                logging.info("Window icon set successfully.")
            except Exception as e:
                logging.error(f"Failed to set window icon from {icon_path}: {e}", exc_info=True)
        else:
            logging.warning("Icon file 'editor_icon.ico' not found.")

    def _init_ui(self):
        """Initializes the main user interface components."""
        logging.debug("Initializing UI...")
        self._create_menu_bar()
        self._create_main_splitter()
        logging.debug("UI Initialization complete.")

    def _create_menu_bar(self):
        """Creates the main menu bar and actions."""
        logging.debug("Creating menu bar...")
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File") # Use '&' for mnemonics

        self.open_action = QAction(QIcon.fromTheme("document-open"), "&Open Folder...", self) # Add icon hint
        self.open_action.setToolTip("Open a folder containing Witcher 3 XML definition files")
        file_menu.addAction(self.open_action)

        self.save_action = QAction(QIcon.fromTheme("document-save"), "&Save", self)
        self.save_action.setToolTip("Save changes to the currently selected file (Ctrl+S)")
        file_menu.addAction(self.save_action)

        self.save_as_action = QAction(QIcon.fromTheme("document-save-as"), "Save &As...", self)
        self.save_as_action.setToolTip("Save the current file to a new location")
        file_menu.addAction(self.save_as_action)

        self.save_all_action = QAction(QIcon.fromTheme("document-save-all"), "Save A&ll", self)
        self.save_all_action.setToolTip("Save all modified files (Ctrl+Shift+S)")
        file_menu.addAction(self.save_all_action)

        file_menu.addSeparator()

        # Use standard exit action
        exit_action = QAction(QIcon.fromTheme("application-exit"), "E&xit", self)
        exit_action.setToolTip("Exit the application")
        exit_action.triggered.connect(self.close) # Connect directly to close
        file_menu.addAction(exit_action)

        help_menu = menu_bar.addMenu("&Help")
        self.author_action = QAction("&About...", self) # Changed text slightly
        self.author_action.setToolTip("Show information about the editor")
        help_menu.addAction(self.author_action)

    def _create_main_splitter(self):
        """Creates the main horizontal splitter and its panes."""
        logging.debug("Creating main splitter...")
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        self._create_left_pane(splitter)
        self._create_right_pane(splitter)

        splitter.setSizes([300, 900]) # Initial size ratio

    def _create_left_pane(self, parent_splitter):
        """Creates the left pane containing tabs, lists, and action buttons."""
        logging.debug("Creating left pane...")
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)

        self.tab_widget = QTabWidget()
        left_layout.addWidget(self.tab_widget)

        # Abilities Tab
        self.ability_tab = QWidget()
        ability_layout = QVBoxLayout(self.ability_tab)
        self.ability_filter = QLineEdit()
        self.ability_filter.setPlaceholderText("Filter abilities by name...")
        self.ability_list = QListWidget()
        self.ability_list.setObjectName("AbilityList")
         # ---- vvv ADDED vvv ----
        self.ability_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # ---- ^^^ ADDED ^^^ ----
        ability_layout.addWidget(self.ability_filter)
        ability_layout.addWidget(self.ability_list)
        self.tab_widget.addTab(self.ability_tab, "Abilities")

        # Items Tab
        self.item_tab = QWidget()
        item_layout = QVBoxLayout(self.item_tab)
        self.item_filter = QLineEdit()
        self.item_filter.setPlaceholderText("Filter items by name...")
        self.item_list = QListWidget()
        self.item_list.setObjectName("ItemList")
        # ---- vvv ADDED vvv ----
        self.item_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # ---- ^^^ ADDED ^^^ ----
        item_layout.addWidget(self.item_filter)
        item_layout.addWidget(self.item_list)
        self.tab_widget.addTab(self.item_tab, "Items")

        # Action Buttons
        button_layout = QHBoxLayout()
        self.add_button = QPushButton(QIcon.fromTheme("list-add"), "Add")
        self.add_button.setToolTip("Add a new Ability or Item")
        self.remove_button = QPushButton(QIcon.fromTheme("list-remove"), "Remove")
        self.remove_button.setToolTip("Remove the selected Ability or Item")
        self.duplicate_button = QPushButton(QIcon.fromTheme("edit-copy"), "Duplicate")
        self.duplicate_button.setToolTip("Duplicate the selected Ability or Item")
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.remove_button)
        button_layout.addWidget(self.duplicate_button)
        left_layout.addLayout(button_layout)

        parent_splitter.addWidget(left_widget)

    def _create_right_pane(self, parent_splitter):
        """Creates the right pane containing the details editor."""
        logging.debug("Creating right pane...")
        right_scroll_area = QScrollArea()
        right_scroll_area.setWidgetResizable(True)
        right_scroll_area.setObjectName("DetailsScrollArea")

        self.right_widget = QWidget() # Main container widget inside scroll area
        self.right_layout = QVBoxLayout(self.right_widget)
        self.right_layout.setContentsMargins(10, 10, 10, 10)
        self.right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.right_layout.setSpacing(10) # Add some spacing between sections
        right_scroll_area.setWidget(self.right_widget)

        # --- Common Fields ---
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        self.name_input.setReadOnly(True) # Name is usually key, edited via duplicate/add
        self.name_input.setObjectName("NameInput")
        name_layout.addWidget(self.name_input)
        self.right_layout.addLayout(name_layout)

        tags_layout = QHBoxLayout()
        tags_layout.addWidget(QLabel("Tags:"))
        self.tags_input = QLineEdit()
        self.tags_input.setToolTip("Comma-separated list of tags")
        self.tags_input.setObjectName("TagsInput")
        # Attach completer AFTER adding widget (done in populate/connect signals)
        tags_layout.addWidget(self.tags_input)
        self.right_layout.addLayout(tags_layout)

        # --- Item Specific Sections & Buttons ---
        self.item_attributes_header = self._create_section_header("Item Attributes")
        self.item_attributes_section = QWidget()
        self.item_attributes_layout = QGridLayout(self.item_attributes_section)
        self.item_attributes_layout.setObjectName("ItemAttributesLayout")
        self.item_attributes_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.right_layout.addWidget(self.item_attributes_header)
        self.right_layout.addWidget(self.item_attributes_section)
        # Button to add item attribute is added *inside* _populate_item_attributes

        self.base_abilities_header = self._create_section_header("Base Abilities")
        self.base_abilities_section = QWidget()
        self.base_abilities_layout = QVBoxLayout(self.base_abilities_section)
        self.base_abilities_layout.setObjectName("BaseAbilitiesLayout")
        self.base_abilities_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.right_layout.addWidget(self.base_abilities_header)
        self.right_layout.addWidget(self.base_abilities_section)
        self.add_base_ability_button = QPushButton(QIcon.fromTheme("list-add"), "Add Base Ability")
        self.add_base_ability_button.setToolTip("Add an ability reference required by this item")
        self.right_layout.addWidget(self.add_base_ability_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.recycling_parts_header = self._create_section_header("Recycling Parts")
        self.recycling_parts_section = QWidget()
        self.recycling_parts_layout = QVBoxLayout(self.recycling_parts_section)
        self.recycling_parts_layout.setObjectName("RecyclingPartsLayout")
        self.recycling_parts_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.right_layout.addWidget(self.recycling_parts_header)
        self.right_layout.addWidget(self.recycling_parts_section)
        self.add_recycling_part_button = QPushButton(QIcon.fromTheme("list-add"), "Add Recycling Part")
        self.add_recycling_part_button.setToolTip("Add an item obtained when dismantling this item")
        self.right_layout.addWidget(self.add_recycling_part_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.variants_header = self._create_section_header("Variants")
        self.variants_section = QWidget()
        self.variants_layout = QVBoxLayout(self.variants_section)
        self.variants_layout.setObjectName("VariantsLayout")
        self.variants_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.right_layout.addWidget(self.variants_header)
        self.right_layout.addWidget(self.variants_section)
        self.add_variant_button = QPushButton(QIcon.fromTheme("list-add"), "Add Variant")
        self.add_variant_button.setToolTip("Add a visual or stat variant for this item")
        self.right_layout.addWidget(self.add_variant_button, alignment=Qt.AlignmentFlag.AlignLeft)

        # --- Generic Properties Section (for Abilities) ---
        self.properties_header = self._create_section_header("Properties")
        self.properties_section = QWidget()
        self.properties_layout = QVBoxLayout(self.properties_section)
        self.properties_layout.setObjectName("PropertiesLayout")
        self.properties_layout.setContentsMargins(10, 5, 0, 5) # Indent slightly
        self.properties_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.right_layout.addWidget(self.properties_header)
        self.right_layout.addWidget(self.properties_section)
        self.add_property_button = QPushButton(QIcon.fromTheme("list-add"), "Add Property")
        self.add_property_button.setToolTip("Add a generic property (stat modifier, effect, etc.) to this ability")
        self.right_layout.addWidget(self.add_property_button, alignment=Qt.AlignmentFlag.AlignLeft)

        # Initial visibility setup
        self.set_item_specific_visibility(False)
        self.set_ability_specific_visibility(False)

        # Stretch at the bottom to push content up
        self.right_layout.addStretch(1)
        parent_splitter.addWidget(right_scroll_area)

    def _create_section_header(self, text):
        """Creates a standard section header widget (Label + Line)."""
        header_label = QLabel(f"<b>{text}</b>") # Make header bold
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 5, 0, 2) # Add some vertical margin
        layout.setSpacing(2)
        layout.addWidget(header_label)
        layout.addWidget(line)

        container = QWidget()
        container.setLayout(layout)
        return container

    def set_item_specific_visibility(self, visible):
        """Shows/hides all item-specific sections and buttons."""
        logging.debug(f"Setting item-specific section visibility to: {visible}")
        self.item_attributes_header.setVisible(visible)
        self.item_attributes_section.setVisible(visible)
        self.base_abilities_header.setVisible(visible)
        self.base_abilities_section.setVisible(visible)
        self.add_base_ability_button.setVisible(visible)
        self.recycling_parts_header.setVisible(visible)
        self.recycling_parts_section.setVisible(visible)
        self.add_recycling_part_button.setVisible(visible)
        self.variants_header.setVisible(visible)
        self.variants_section.setVisible(visible)
        self.add_variant_button.setVisible(visible)

    def set_ability_specific_visibility(self, visible):
        """Shows/hides ability-specific (generic properties) section."""
        logging.debug(f"Setting ability-specific section visibility to: {visible}")
        self.properties_header.setVisible(visible)
        self.properties_section.setVisible(visible)
        self.add_property_button.setVisible(visible)

    def _connect_signals(self):
        """Connects UI signals to their corresponding slots."""
        logging.debug("Connecting signals...")

        # --- Left Pane Signals ---
        self.ability_list.currentItemChanged.connect(lambda current, _: self.list_item_selected(current, TAG_ABILITY))
        self.item_list.currentItemChanged.connect(lambda current, _: self.list_item_selected(current, TAG_ITEM))
        self.ability_filter.textChanged.connect(self.filter_abilities)
        self.item_filter.textChanged.connect(self.filter_items)
        self.add_button.clicked.connect(self.add_entry)
        self.remove_button.clicked.connect(self.remove_entry)
        self.duplicate_button.clicked.connect(self.duplicate_entry)

        # --- Menu Action Signals ---
        if self.open_action: self.open_action.triggered.connect(self.open_folder)
        else: logging.warning("self.open_action not initialized.")

        if self.save_action: self.save_action.triggered.connect(self.save_current_file)
        else: logging.warning("self.save_action not initialized.")

        if self.save_all_action: self.save_all_action.triggered.connect(self.save_all_files)
        else: logging.warning("self.save_all_action not initialized.")

        if self.save_as_action: self.save_as_action.triggered.connect(self.save_as_current_file)
        else: logging.warning("self.save_as_action not initialized.")

        if self.author_action: self.author_action.triggered.connect(self.show_author_info)
        else: logging.warning("self.author_action not initialized.")

        # Exit action connected directly in _create_menu_bar

        # --- Right Pane Editing Signals ---
        # Common fields
        self.tags_input.editingFinished.connect(self.tags_changed)
        # Completer attached here for tags_input as it's always visible
        self._attach_completer(self.tags_input, self.tag_model, "Tags")

        # Section-specific add buttons
        self.add_property_button.clicked.connect(self.add_property)
        self.add_base_ability_button.clicked.connect(self.add_base_ability)
        self.add_recycling_part_button.clicked.connect(self.add_recycling_part)
        self.add_variant_button.clicked.connect(self.add_variant)

        # Signals for dynamically created widgets (attributes, parts, etc.)
        # are connected when those widgets are created (e.g., in populate_*, add_* methods)

        logging.debug("Signal connections complete.")
        
    def _connect_context_menu_signals(self):
        """Connects signals for custom context menus."""
        logging.debug("Connecting context menu signals...")
        self.ability_list.customContextMenuRequested.connect(
            lambda pos: self._show_list_context_menu(self.ability_list, pos)
        )
        self.item_list.customContextMenuRequested.connect(
            lambda pos: self._show_list_context_menu(self.item_list, pos)
        )
        logging.debug("Context menu signal connections complete.")

# --- Context Menu Handling ---

    def _show_list_context_menu(self, list_widget: QListWidget, pos: QPoint):
        """Creates and displays a context menu for the ability/item lists."""
        item = list_widget.itemAt(pos)
        # Only show menu if clicking on an item that matches the current selection
        if item is None or item.text() != self.current_selection_name:
            logging.debug("Context menu requested but not on the currently selected item, ignoring.")
            # Optionally show a default menu or no menu
            return

        if not self.current_selection_filepath:
             logging.debug("Context menu requested, but no valid file path associated with selection.")
             return

        menu = QMenu(self)
        open_action = QAction(QIcon.fromTheme("folder-open"), "Open File Location", self)
        open_action.setToolTip(f"Show '{os.path.basename(self.current_selection_filepath)}' in the file explorer")
        open_action.triggered.connect(self._open_current_file_location)

        # Ensure the file actually exists before enabling the action
        is_enabled = False
        try:
            is_enabled = Path(self.current_selection_filepath).is_file()
        except Exception:
            pass # Ignore errors checking path, action will remain disabled
        open_action.setEnabled(is_enabled)

        menu.addAction(open_action)
        # Add other actions here if needed in the future (e.g., copy name, etc.)

        # Show the menu at the cursor position
        global_pos = list_widget.mapToGlobal(pos)
        menu.exec(global_pos)

    def _open_current_file_location(self):
        """Opens the system file explorer to the location of the current file."""
        if not self.current_selection_filepath:
            logging.warning("Attempted to open file location, but no file is selected.")
            return

        file_path_str = self.current_selection_filepath
        file_path = Path(file_path_str)

        logging.info(f"Attempting to open file location for: {file_path_str}")

        if not file_path.is_file():
            logging.error(f"Cannot open file location: File does not exist at '{file_path_str}'.")
            QMessageBox.warning(self, "File Not Found", f"The file could not be found at the expected location:\n{file_path_str}")
            return

        try:
            if sys.platform == "win32":
                # Use explorer /select to highlight the file
                cmd = ['explorer', '/select,', str(file_path)]
                logging.debug(f"Executing command: {cmd}")
                subprocess.Popen(cmd)
            elif sys.platform == "darwin": # macOS
                # Use open -R to reveal the file in Finder
                cmd = ['open', '-R', str(file_path)]
                logging.debug(f"Executing command: {cmd}")
                subprocess.Popen(cmd)
            else: # Linux and other Unix-like
                # Best cross-DE approach is to open the containing directory
                parent_dir = file_path.parent
                cmd = ['xdg-open', str(parent_dir)]
                logging.debug(f"Executing command: {cmd}")
                subprocess.Popen(cmd)
            logging.info(f"Successfully requested file explorer for: {file_path_str}")
        except FileNotFoundError:
             logging.error(f"Could not execute file explorer command. Is the command (explorer/open/xdg-open) in your PATH?", exc_info=True)
             QMessageBox.critical(self, "Error", "Could not find the necessary command to open the file explorer.\nPlease ensure it's installed and in your system's PATH.")
        except Exception as e:
            logging.error(f"Failed to open file location '{file_path_str}': {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"An unexpected error occurred while trying to open the file location:\n{e}")


    def _setup_shortcuts(self):
        """Sets up global keyboard shortcuts."""
        logging.debug("Setting up shortcuts...")
        save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        save_shortcut.activated.connect(self.save_current_file)
        save_all_shortcut = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        save_all_shortcut.activated.connect(self.save_all_files)
        logging.debug("Shortcuts set.")

    def show_author_info(self):
        """Displays an information box about the author."""
        author_text = """<b>Witcher 3 XML Editor v1.0</b><br>
        -------------------------------------<br>
        Created by Gerwant. Thank you for using this tool.<br><br>
        Feel free to visit:<br>
        <a href="https://next.nexusmods.com/profile/gerwant30">Nexus Mods</a><br>
        <a href="https://www.youtube.com/@TalesoftheWitcher">YouTube</a><br><br>
        
        If you like my work, you can support me at:<br>
        <a href="https://ko-fi.com/gerwant_totw">Ko-fi</a><br>
        <a href="https://www.patreon.com/TalesofTheWitcher">Patreon</a><br>
        Cheers!"""

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("About Witcher 3 XML Editor")
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setTextFormat(Qt.TextFormat.RichText)  # Użyj RichText
        msg_box.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction | 
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        msg_box.setText(author_text)
        msg_box.exec()

    # --- Configuration Handling ---

    def load_config(self):
        """Loads configuration (last folder) from the ini file."""
        config = configparser.ConfigParser()
        self.last_folder = "" # Reset before loading
        if not self.config_file.exists():
            logging.warning(f"Config file {self.config_file} not found. Will be created on save.")
            return

        try:
            config.read(self.config_file, encoding='utf-8') # Use utf-8 common standard
            if 'Settings' in config and 'LastFolder' in config['Settings']:
                folder = config['Settings']['LastFolder']
                if folder and Path(folder).is_dir(): # Check if it's a valid directory
                    self.last_folder = folder
                    logging.info(f"Loaded last folder from config: {self.last_folder}")
                elif folder:
                    logging.warning(f"LastFolder path in config ('{folder}') is not a valid directory. Ignoring.")
                else:
                    logging.info("Config 'LastFolder' entry is empty.")
            else:
                logging.warning("Config file missing [Settings] section or 'LastFolder' key.")
        except configparser.Error as e:
            logging.error(f"Error reading config file {self.config_file}: {e}", exc_info=True)
        except Exception as e:
            logging.error(f"Unexpected error loading config: {e}", exc_info=True)

    def save_config(self):
        """Saves the current configuration (last folder) to the ini file."""
        config = configparser.ConfigParser()
        try:
            # Read existing file first to preserve other settings (if any)
            if self.config_file.exists():
                try:
                    config.read(self.config_file, encoding='utf-8')
                except configparser.Error as e:
                    logging.warning(f"Could not read existing config file {self.config_file} before saving: {e}. Overwriting.")
                    config = configparser.ConfigParser() # Start fresh if read fails

            if 'Settings' not in config:
                config['Settings'] = {}

            config['Settings']['LastFolder'] = self.last_folder if self.last_folder else ""
            logging.info(f"Saving config: LastFolder = '{config['Settings']['LastFolder']}'")

            with open(self.config_file, 'w', encoding='utf-8') as configfile:
                config.write(configfile)
            logging.info(f"Configuration saved to: {self.config_file}")

        except IOError as e:
            logging.error(f"Error writing config file {self.config_file}: {e}", exc_info=True)
            QMessageBox.warning(self, "Configuration Error", f"Could not save configuration file:\n{e}")
        except Exception as e:
            logging.error(f"Unexpected error saving config: {e}", exc_info=True)

    def load_folder_on_startup(self, folder_path):
        """Attempts to load XML files from the given folder on startup."""
        self.statusBar.showMessage(f"Auto-loading files from: {folder_path}...")
        QApplication.processEvents() # Update UI to show message
        try:
            success = self.load_xml_files(folder_path)
            if success:
                self.populate_lists()
                self.statusBar.showMessage(f"Loaded files from: {folder_path}. Select an element.", 5000)
            else:
                # load_xml_files should have logged errors
                self.statusBar.showMessage("Failed to load files automatically. See logs.", 5000)
                self.last_folder = "" # Clear invalid folder
        except Exception as e:
             error_msg = f"Unexpected error during auto-load from {folder_path}:\n{e}"
             logging.error(error_msg, exc_info=True)
             QMessageBox.critical(self, "Auto-load Error", error_msg)
             self.statusBar.showMessage("Error during automatic file loading.", 5000)
             self.last_folder = "" # Clear invalid folder

    # --- File Operations ---

    def open_folder(self):
        """Opens a folder selection dialog and loads XML files."""
        logging.info("Open Folder action triggered...")

        if self._check_unsaved_changes("open a new folder") == QMessageBox.StandardButton.Cancel:
            return # User cancelled

        # Determine starting directory for the dialog
        start_dir = self.base_path
        if self.last_folder and Path(self.last_folder).is_dir():
            start_dir = self.last_folder
            logging.debug(f"Opening file dialog in last used folder: {start_dir}")
        else:
            logging.debug(f"No valid last folder. Opening file dialog in base path: {start_dir}")

        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Folder Containing Witcher 3 XML Files",
            str(start_dir) # QFileDialog needs a string path
        )

        if folder_path:
            selected_path = Path(folder_path)
            logging.info(f"Folder selected: {selected_path}")

            if selected_path.is_dir():
                 new_last_folder = str(selected_path)
                 if self.last_folder != new_last_folder:
                     self.last_folder = new_last_folder
                     self.save_config() # Save the newly selected folder

                 self.statusBar.showMessage(f"Loading files from: {selected_path}..."); QApplication.processEvents()
                 try:
                     success = self.load_xml_files(selected_path) # Pass Path object
                     if success:
                         self.populate_lists()
                         self.statusBar.showMessage(f"Loaded files from: {selected_path}. Select an element.", 5000)
                     else:
                         self.statusBar.showMessage("Failed to load some files. Check logs.", 5000)
                         # Don't clear last_folder here, loading might have partially succeeded
                 except Exception as e:
                      error_msg = f"Unexpected error occurred while loading files from {selected_path}:\n{e}"
                      logging.error(error_msg, exc_info=True)
                      QMessageBox.critical(self, "Loading Error", error_msg)
                      self.statusBar.showMessage("Error during file loading.", 5000)
                      # If a major error occurred during load, maybe clear the last folder
                      # if self.last_folder == new_last_folder:
                      #     self.last_folder = ""
                      #     self.save_config()
            else:
                 # Should not happen with getExistingDirectory, but check anyway
                 logging.warning(f"QFileDialog returned a path that is not a directory: {selected_path}")
                 QMessageBox.warning(self, "Error", "The selected path is not a valid folder.")
        else:
             logging.info("Folder selection cancelled by user.")
             self.statusBar.showMessage("Folder opening cancelled.", 3000)

    def load_xml_files(self, folder_path):
        """Loads all XML files from the specified folder path (Path object)."""
        self.clear_data() # Clear previous data first
        logging.info(f"Starting XML file loading from: {folder_path}")
        file_count = 0
        ability_count = 0
        item_count = 0
        processed_files = 0
        errors_occurred = False

        # Use temporary sets to collect data during parsing
        temp_sets = {
            "prop_names": set(), "item_attr_names": set(), "variant_attr_names": set(),
            "prop_attr_names": set(), "tags": set(), "ability_names": set(), "item_names": set(),
            "recycling_parts": set(), "item_categories": set(), "ability_modes": set(),
            "variant_nested_tags": set(), "equip_templates": set(), "loc_keys": set(),
            "icon_paths": set(), "prop_attr_types": set(), "equip_slots": set(),
            "hold_slots": set(), "hands": set(), "sound_ids": set(), "events": set(),
            "anim_actions": set()
        }

        try:
            for root_dir, _, files in os.walk(folder_path):
                for filename in files:
                    if filename.lower().endswith(".xml"):
                        file_path = Path(root_dir) / filename
                        file_count += 1
                        tree, root = self._parse_xml_file(str(file_path)) # Pass string path to helper
                        if tree and root:
                            processed_files += 1
                            self.loaded_files[str(file_path)] = {'tree': tree, 'root': root}
                            a_added, i_added = self._process_xml_root(root, str(file_path), temp_sets)
                            ability_count += a_added
                            item_count += i_added
                        else:
                            errors_occurred = True # Mark error if parsing failed

            self._update_internal_sets(temp_sets)
            self._update_all_completer_models()

            logging.info(f"Finished loading. Parsed {processed_files}/{file_count} XML files.")
            logging.info(f"  Found {ability_count} unique abilities ({len(self.all_ability_names)} total names).")
            logging.info(f"  Found {item_count} unique items ({len(self.all_item_names)} total names).")
            # Add more summary logs if needed

        except Exception as e:
            logging.error(f"Critical error during file walking or processing in {folder_path}: {e}", exc_info=True)
            QMessageBox.critical(self, "Loading Error", f"A critical error occurred during file loading:\n{e}")
            errors_occurred = True

        return not errors_occurred # Return True if successful (no errors)

    def _parse_xml_file(self, file_path_str):
        """Parses a single XML file, returns (tree, root) or (None, None)."""
        try:
            # Remove comments during parsing, keep processing instructions
            parser = ET.XMLParser(remove_comments=True, remove_pis=False, resolve_entities=False)
            tree = ET.parse(file_path_str, parser=parser)
            root = tree.getroot()
            if root is None:
                logging.warning(f"Empty root element in file: {file_path_str}")
                return None, None
            # logging.debug(f"Successfully parsed: {file_path_str}")
            return tree, root
        except ET.XMLSyntaxError as e:
            logging.error(f"XML Syntax Error in {file_path_str}: {e}")
            return None, None
        except Exception as e:
            logging.error(f"Unexpected error parsing {file_path_str}: {e}", exc_info=True)
            return None, None

    def _process_xml_root(self, root, file_path, temp_sets):
        """Processes abilities and items within a single XML root."""
        abilities_added = 0
        items_added = 0
        # Use findall with XPath to be slightly more robust to structure variations
        for abilities_node in root.findall(f'.//{TAG_ABILITIES}'):
             abilities_added += self._process_abilities_node(abilities_node, file_path, temp_sets)
        for items_node in root.findall(f'.//{TAG_ITEMS}'):
             items_added += self._process_items_node(items_node, file_path, temp_sets)
        return abilities_added, items_added

    def _process_abilities_node(self, abilities_node, file_path, temp_sets):
        """Processes <ability> elements and collects data."""
        count = 0
        for ability in abilities_node.findall(TAG_ABILITY):
            name = ability.get('name')
            if name:
                if name not in self.abilities_map:
                    self.abilities_map[name] = {'filepath': file_path, 'element': ability}
                    count += 1
                else:
                    # Handle duplicates? Log warning? Overwrite? For now, log.
                    logging.warning(f"Duplicate ability name '{name}' found. Using entry from {self.abilities_map[name]['filepath']}. Ignoring entry from {file_path}")

                temp_sets["ability_names"].add(name)
                # Collect tags, property names, attribute names etc. from ability children
                for prop in ability:
                    if ET.iselement(prop): # Check if it's an element (not comment, etc.)
                        tag = prop.tag
                        if tag == TAG_TAGS:
                             if prop.text: temp_sets["tags"].update(t.strip() for t in prop.text.split(',') if t.strip())
                        elif tag not in self.KNOWN_ABILITY_CHILD_TAGS: # Treat unknown tags as properties
                             temp_sets["prop_names"].add(tag)
                             temp_sets["prop_attr_names"].update(prop.attrib.keys())
                             prop_type = prop.get('type')
                             if prop_type: temp_sets["prop_attr_types"].add(prop_type)
        return count

    def _process_items_node(self, items_node, file_path, temp_sets):
        """Processes <item> elements and collects data."""
        count = 0
        for item in items_node.findall(TAG_ITEM):
             name = item.get('name')
             if name:
                 if name not in self.items_map:
                     self.items_map[name] = {'filepath': file_path, 'element': item}
                     count += 1
                 else:
                     logging.warning(f"Duplicate item name '{name}' found. Using entry from {self.items_map[name]['filepath']}. Ignoring entry from {file_path}")

                 temp_sets["item_names"].add(name)
                 temp_sets["item_attr_names"].update(item.attrib.keys())

                 # Collect specific attribute values for completers
                 self._collect_item_attribute_values(item, temp_sets)

                 # Process known children (tags, variants, etc.)
                 for child in item:
                     if ET.iselement(child):
                         tag = child.tag
                         if tag == TAG_TAGS:
                             if child.text: temp_sets["tags"].update(t.strip() for t in child.text.split(',') if t.strip())
                         elif tag == TAG_RECYCLING_PARTS:
                             for part in child.findall(TAG_PARTS):
                                 if part.text: temp_sets["recycling_parts"].add(part.text.strip())
                         elif tag == TAG_VARIANTS:
                             for variant in child.findall(TAG_VARIANT):
                                 temp_sets["variant_attr_names"].update(variant.attrib.keys())
                                 var_eq_tmpl = variant.get('equip_template')
                                 if var_eq_tmpl: temp_sets["equip_templates"].add(var_eq_tmpl)
                                 for nested in variant:
                                     if ET.iselement(nested): temp_sets["variant_nested_tags"].add(nested.tag)
                         elif tag not in self.KNOWN_ITEM_CHILD_TAGS: # Treat as generic property if not known structure
                              logging.debug(f"Found potentially generic property '{tag}' under item '{name}'")
                              temp_sets["prop_names"].add(tag)
                              temp_sets["prop_attr_names"].update(child.attrib.keys())
                              # Could also collect property types here if needed
        return count

    def _collect_item_attribute_values(self, item_element, temp_sets):
        """Helper to collect specific attribute values from an <item> element."""
        # Helper to safely add if value exists
        def add_if_present(attr_name, target_set):
            value = item_element.get(attr_name)
            if value: target_set.add(value)

        add_if_present('category', temp_sets["item_categories"])
        add_if_present('ability_mode', temp_sets["ability_modes"])
        add_if_present('equip_template', temp_sets["equip_templates"])
        add_if_present('equip_slot', temp_sets["equip_slots"])
        add_if_present('hold_slot', temp_sets["hold_slots"])
        add_if_present('hand', temp_sets["hands"])
        add_if_present('sound_identification', temp_sets["sound_ids"])
        add_if_present('draw_event', temp_sets["events"])
        add_if_present('holster_event', temp_sets["events"])
        add_if_present('draw_act', temp_sets["anim_actions"])
        add_if_present('draw_deact', temp_sets["anim_actions"])
        add_if_present('holster_act', temp_sets["anim_actions"])
        add_if_present('holster_deact', temp_sets["anim_actions"])
        add_if_present('localisation_key_name', temp_sets["loc_keys"])
        add_if_present('localisation_key_description', temp_sets["loc_keys"])
        add_if_present('icon_path', temp_sets["icon_paths"])

    def _update_internal_sets(self, temp_sets):
        """Updates the main self.all_* sets from the temporary collection."""
        logging.debug("Updating internal autocompletion sets...")
        self.all_property_names = temp_sets["prop_names"]
        self.all_item_attribute_names = temp_sets["item_attr_names"]
        self.all_variant_attribute_names = temp_sets["variant_attr_names"]
        self.all_property_attribute_names = temp_sets["prop_attr_names"]
        self.all_tags = temp_sets["tags"]
        self.all_ability_names = temp_sets["ability_names"]
        self.all_item_names = temp_sets["item_names"]
        self.all_recycling_part_names = temp_sets["recycling_parts"]
        self.all_item_categories = temp_sets["item_categories"]
        self.all_ability_modes = temp_sets["ability_modes"]
        self.all_variant_nested_tags = temp_sets["variant_nested_tags"]
        self.all_equip_templates = temp_sets["equip_templates"]
        self.all_loc_keys = temp_sets["loc_keys"]
        self.all_icon_paths = temp_sets["icon_paths"]
        self.all_prop_attr_types = temp_sets["prop_attr_types"]
        self.all_equip_slots = temp_sets["equip_slots"]
        self.all_hold_slots = temp_sets["hold_slots"]
        self.all_hands = temp_sets["hands"]
        self.all_sound_ids = temp_sets["sound_ids"]
        self.all_events = temp_sets["events"]
        self.all_anim_actions = temp_sets["anim_actions"]
        logging.debug("Internal sets updated.")

    def _safe_sorted_string_list(self, data_set, set_name="unknown"):
        """Safely converts a set to a sorted list of strings, logging non-strings."""
        string_list = []
        invalid_items_count = 0
        for item in data_set:
            if isinstance(item, str):
                string_list.append(item)
            else:
                if invalid_items_count < 10: # Log first few offenders
                   logging.warning(f"Non-string item found in completer set '{set_name}': {repr(item)} (type: {type(item).__name__}). Skipping.")
                invalid_items_count += 1
        if invalid_items_count > 10:
            logging.warning(f"Found {invalid_items_count} total non-string items in completer set '{set_name}'.")

        try:
            return sorted(string_list)
        except TypeError as e_sort:
            logging.error(f"Sorting error for completer set '{set_name}' (even after filtering strings!): {e_sort}. List: {string_list}", exc_info=True)
            return string_list # Return unsorted on error

    def _update_single_completer_model(self, model, data_set, model_name):
        """Updates a single QStringListModel safely."""
        try:
            sorted_list = self._safe_sorted_string_list(data_set, model_name)
            model.setStringList(sorted_list)
            # logging.debug(f"Updated completer model '{model_name}' with {len(sorted_list)} items.")
        except Exception as e:
            logging.error(f"Failed to update completer model '{model_name}': {e}", exc_info=True)

    def _update_all_completer_models(self):
        """Updates all QStringListModels from the self.all_* sets."""
        logging.info("Updating all completer models...")
        self._update_single_completer_model(self.item_attribute_name_model, self.all_item_attribute_names, "item_attribute_name")
        self._update_single_completer_model(self.variant_attribute_name_model, self.all_variant_attribute_names, "variant_attribute_name")
        self._update_single_completer_model(self.property_attribute_name_model, self.all_property_attribute_names, "property_attribute_name")
        self._update_single_completer_model(self.ability_name_model, self.all_ability_names, "ability_name")
        self._update_single_completer_model(self.item_name_model, self.all_item_names, "item_name")
        self._update_single_completer_model(self.recycling_part_name_model, self.all_recycling_part_names, "recycling_part_name")
        self._update_single_completer_model(self.item_category_model, self.all_item_categories, "item_category")
        self._update_single_completer_model(self.ability_mode_model, self.all_ability_modes, "ability_mode")
        self._update_single_completer_model(self.variant_nested_tag_model, self.all_variant_nested_tags, "variant_nested_tag")
        self._update_single_completer_model(self.tag_model, self.all_tags, "tag")
        self._update_single_completer_model(self.property_name_model, self.all_property_names, "property_name")
        self._update_single_completer_model(self.equip_template_model, self.all_equip_templates, "equip_template")
        self._update_single_completer_model(self.localisation_key_model, self.all_loc_keys, "localisation_key")
        self._update_single_completer_model(self.icon_path_model, self.all_icon_paths, "icon_path")
        self._update_single_completer_model(self.property_attr_type_model, self.all_prop_attr_types, "property_attr_type")
        self._update_single_completer_model(self.equip_slot_model, self.all_equip_slots, "equip_slot")
        self._update_single_completer_model(self.hold_slot_model, self.all_hold_slots, "hold_slot")
        self._update_single_completer_model(self.hand_model, self.all_hands, "hand")
        self._update_single_completer_model(self.sound_id_model, self.all_sound_ids, "sound_id")
        self._update_single_completer_model(self.event_model, self.all_events, "event")
        self._update_single_completer_model(self.anim_action_model, self.all_anim_actions, "anim_action")
        # Static models (boolean, enhancement_slots) don't need updating
        logging.info("Completer models update finished.")

    def save_file(self, file_path):
        """Saves the XML tree associated with the given file path."""
        if file_path not in self.loaded_files:
            logging.warning(f"Attempted to save non-loaded file: {file_path}")
            return False
        if file_path not in self.modified_files:
            # logging.debug(f"File not modified, skipping save: {file_path}")
            return True # Not an error, just nothing to save

        tree = self.loaded_files[file_path]['tree']
        logging.info(f"Saving file: {file_path}")
        try:
            # Ensure parent directory exists
            parent_dir = Path(file_path).parent
            parent_dir.mkdir(parents=True, exist_ok=True)

            tree.write(file_path,
                       pretty_print=True,         # Indentation and newlines
                       encoding='utf-16',         # Preserve original encoding
                       xml_declaration=True)      # Include <?xml ...?>
            self.modified_files.remove(file_path)
            self.statusBar.showMessage(f"Saved: {os.path.basename(file_path)}", 3000)
            logging.info(f"Successfully saved: {file_path}")
            # Update window title if this was the current file
            if file_path == self.current_selection_filepath:
                self.update_window_title()
            return True
        except IOError as e:
             logging.error(f"IOError saving file {file_path}: {e}", exc_info=True)
             QMessageBox.critical(self, "Save Error", f"Could not write to file:\n{file_path}\n\nError: {e}")
             return False
        except Exception as e:
             logging.error(f"Unexpected error saving file {file_path}: {e}", exc_info=True)
             QMessageBox.critical(self, "Save Error", f"An unexpected error occurred while saving:\n{file_path}\n\nError: {e}")
             return False

    def save_current_file(self):
        """Saves the currently selected file."""
        logging.debug("Save Current File action triggered.")
        if self.current_selection_filepath:
            self.save_file(self.current_selection_filepath)
            # save_file handles status bar and title update
        else:
            logging.warning("Save Current File called, but no file selected.")
            QMessageBox.information(self, "Save", "No item or ability is currently selected.")

    def save_all_files(self):
        """Saves all files marked as modified."""
        logging.debug("Save All Files action triggered.")
        if not self.modified_files:
            logging.info("Save All: No modified files to save.")
            QMessageBox.information(self, "Save All", "There are no unsaved changes.")
            return

        modified_count = len(self.modified_files)
        reply = QMessageBox.question(self, "Save All", f"Save changes to {modified_count} file(s)?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.Yes)

        if reply == QMessageBox.StandardButton.Yes:
            logging.info(f"Saving {modified_count} modified files...")
            saved_count = 0
            failed_count = 0
            # Iterate over a copy of the set, as save_file modifies it
            for file_path in list(self.modified_files):
                if self.save_file(file_path):
                    saved_count += 1
                else:
                    failed_count += 1

            msg = f"Saved {saved_count} file(s)."
            if failed_count > 0:
                msg += f" Failed to save {failed_count} file(s). Check logs."
                QMessageBox.warning(self, "Save All Warning", f"Failed to save {failed_count} file(s). Please check the logs for details.")
            else:
                msg += " All changes saved successfully."
            self.statusBar.showMessage(msg, 5000)
            logging.info(msg)
            self.update_window_title() # Update title in case markers change
        else:
            logging.info("Save All cancelled by user.")

    def save_as_current_file(self):
        """Saves the current file's content to a new location and updates state."""
        logging.info("Save As action triggered...")

        if not self.current_selection_filepath or self.current_selection_filepath not in self.loaded_files:
            QMessageBox.information(self, "Save As...", "Please select an item or ability first to determine which file to save.")
            return

        original_filepath = self.current_selection_filepath
        original_name = self.current_selection_name # Remember selection context
        original_type = self.current_selection_type

        # Get the XML tree from memory
        if original_filepath not in self.loaded_files:
            logging.error(f"Save As: Current file path '{original_filepath}' not found in loaded_files.")
            QMessageBox.critical(self, "Internal Error", "Cannot find the data for the selected file.")
            return
        tree = self.loaded_files[original_filepath]['tree']

        # Suggest a new filename
        original_path_obj = Path(original_filepath)
        suggested_name = f"{original_path_obj.stem}_copy{original_path_obj.suffix}"
        start_dir = str(original_path_obj.parent)

        new_filepath_str, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save XML File As...",
            os.path.join(start_dir, suggested_name), # Use os.path.join for compatibility
            "XML Files (*.xml);;All Files (*)"
        )

        if not new_filepath_str:
            logging.info("Save As cancelled by user.")
            self.statusBar.showMessage("Save As cancelled.", 3000)
            return

        new_filepath = Path(new_filepath_str)
        # Ensure .xml extension
        if new_filepath.suffix.lower() != ".xml":
            new_filepath = new_filepath.with_suffix(".xml")
            logging.debug(f"Added .xml suffix. New path: {new_filepath}")

        # --- Save the tree to the new path ---
        logging.info(f"Attempting to save copy to: {new_filepath}")
        try:
            # Ensure parent directory exists
            new_filepath.parent.mkdir(parents=True, exist_ok=True)
            # Use the same writing parameters as save_file
            tree.write(str(new_filepath), pretty_print=True, encoding='utf-16', xml_declaration=True)
            logging.info(f"Successfully saved copy as: {new_filepath}")
            self.statusBar.showMessage(f"Saved as: {new_filepath.name}", 4000)

            # --- Update editor state if saved to a DIFFERENT path ---
            if new_filepath != original_path_obj:
                logging.info(f"Updating editor state for new file: {new_filepath}")
                new_filepath_str = str(new_filepath) # Use string for dict keys

                # Add the new file to loaded_files (shares the tree object initially)
                # Important: Parse the *saved* file to get potentially new element references
                # (though deepcopy might be safer if elements were modified *before* save as)
                saved_tree, saved_root = self._parse_xml_file(new_filepath_str)
                if not saved_tree or not saved_root:
                     logging.error(f"Failed to re-parse the newly saved file '{new_filepath_str}'. State update aborted.")
                     QMessageBox.critical(self, "Save As Error", "Could not re-read the saved file. Editor state might be inconsistent.")
                     return

                self.loaded_files[new_filepath_str] = {'tree': saved_tree, 'root': saved_root}

                # Update maps (abilities_map, items_map)
                # This assumes the *entire content* of the saved file now belongs to the new path
                self._update_maps_for_new_path(original_filepath, new_filepath_str, saved_root, original_type)

                # Remove the *new* file path from modified set (it was just saved)
                if new_filepath_str in self.modified_files:
                    self.modified_files.remove(new_filepath_str)
                    logging.debug(f"Removed new file '{new_filepath_str}' from modified set.")

                # Refresh UI lists (might contain elements now pointing to the new file)
                self.populate_lists()

                # Try to re-select the item/ability by name
                list_widget = self.ability_list if original_type == TAG_ABILITY else self.item_list
                items = list_widget.findItems(original_name, Qt.MatchFlag.MatchExactly)
                if items:
                    logging.debug(f"Re-selecting element '{original_name}' in list.")
                    list_widget.setCurrentItem(items[0])
                    # setCurrentItem triggers list_item_selected -> populate_details
                    # which should now use the updated file path from the map
                else:
                    logging.warning(f"Could not re-select element '{original_name}' after Save As.")
                    self.clear_details_pane() # Clear details if re-selection failed

            else:
                # User saved over the original file
                logging.info(f"Overwrote original file: {original_filepath}")
                # Remove from modified set as it was just saved
                if original_filepath in self.modified_files:
                    self.modified_files.remove(original_filepath)
                self.update_window_title() # Update title (remove asterisk)

        except IOError as e:
             error_msg = f"Could not write file '{new_filepath}':\n{e}"
             logging.error(f"Save As IO Error: {error_msg}", exc_info=True)
             QMessageBox.critical(self, "Save As Error", error_msg)
             self.statusBar.showMessage("Error during Save As.", 4000)
        except Exception as e:
             error_msg = f"An unexpected error occurred during Save As for '{new_filepath}':\n{e}"
             logging.error(f"Save As Unexpected Error: {error_msg}", exc_info=True)
             QMessageBox.critical(self, "Save As Error", error_msg)
             self.statusBar.showMessage("Error during Save As.", 4000)

    def _update_maps_for_new_path(self, old_filepath, new_filepath, new_root_element, entry_type):
        """Updates abilities_map or items_map to point elements to the new file path."""
        logging.debug(f"Updating map ({entry_type}) from '{old_filepath}' to '{new_filepath}'")
        data_map = self.abilities_map if entry_type == TAG_ABILITY else self.items_map
        parent_node_tag = TAG_ABILITIES if entry_type == TAG_ABILITY else TAG_ITEMS
        child_tag = entry_type # 'ability' or 'item'
        updated_count = 0

        # Find the parent node (<abilities> or <items>) in the *newly saved* root
        parent_node = new_root_element.find(f".//{parent_node_tag}")
        if parent_node is None:
            logging.warning(f"Could not find <{parent_node_tag}> node in the newly saved file '{new_filepath}'. Cannot update map references.")
            return

        # Iterate through elements in the *newly saved file's* parent node
        for element in parent_node.findall(child_tag):
            elem_name = element.get('name')
            if not elem_name:
                continue

            # Option 1: If the element name exists in the map, *always* update its path and element ref
            # to the new file, regardless of its previous path. This assumes the saved file
            # is the new source of truth for all its contained elements.
            if elem_name in data_map:
                data_map[elem_name]['filepath'] = new_filepath
                data_map[elem_name]['element'] = element # Update element reference!
                updated_count += 1
                # logging.debug(f"  Updated map entry for '{elem_name}' to point to '{new_filepath}'")
            else:
                # If the element name wasn't in the map before (e.g., added just before Save As)
                # add it now, pointing to the new file.
                data_map[elem_name] = {'filepath': new_filepath, 'element': element}
                updated_count += 1
                logging.debug(f"  Added new map entry for '{elem_name}' pointing to '{new_filepath}'")

            # Option 2 (Alternative - More Conservative):
            # Only update if the element *previously* belonged to the original file path.
            # if elem_name in data_map and data_map[elem_name]['filepath'] == old_filepath:
            #     data_map[elem_name]['filepath'] = new_filepath
            #     data_map[elem_name]['element'] = element
            #     updated_count += 1
            # elif elem_name not in data_map: # Add if completely new
            #     data_map[elem_name] = {'filepath': new_filepath, 'element': element}
            #     updated_count += 1

        logging.info(f"Updated map paths/elements for {updated_count} {entry_type}(s) to '{new_filepath}'.")


    def mark_file_modified(self, file_path):
        """Marks a file as modified and updates the window title."""
        if file_path and file_path not in self.modified_files:
            logging.debug(f"Marking file as modified: {file_path}")
            self.modified_files.add(file_path)
            self.update_window_title() # Update title immediately

    def update_window_title(self):
        """Updates the main window title based on selection and modification status."""
        base_title = "Witcher 3 XML Editor v1.0"
        title = base_title
        asterisk = ""
        plus = ""

        if self.current_selection_filepath:
            title += f" - [{os.path.basename(self.current_selection_filepath)}]"
            if self.current_selection_filepath in self.modified_files:
                asterisk = " (*)" # Current file is modified

        # Check if *any* other file (not the current one) is modified
        other_modified = any(f != self.current_selection_filepath for f in self.modified_files)
        if other_modified and not asterisk: # Show '+' only if current isn't already marked with '*'
             plus = " (+)"

        self.setWindowTitle(title + asterisk + plus)

    # --- UI Population and Updates ---

    def clear_layout(self, layout):
        """Recursively clears all widgets and sub-layouts from a given layout."""
        if layout is None:
            # logging.warning("Attempted to clear a None layout.")
            return
        # Use count() and takeAt(0) which is safer for dynamic layouts
        while layout.count() > 0:
            item = layout.takeAt(0)
            if item is None:
                continue

            widget = item.widget()
            if widget is not None:
                # logging.debug(f"Deleting widget: {widget.objectName() or widget}")
                widget.deleteLater()
            else:
                sub_layout = item.layout()
                if sub_layout is not None:
                    # logging.debug(f"Clearing sub-layout: {sub_layout.objectName() or sub_layout}")
                    self.clear_layout(sub_layout) # Recursive call
        # logging.debug(f"Layout cleared: {layout.objectName() or layout}")


    def clear_details_pane(self):
         """Clears the right-hand details pane and resets selection state."""
         logging.debug("Clearing details pane...")
         # Block signals during clearing
         if self._populating_details:
              # Avoid recursive calls if already populating
              logging.warning("clear_details_pane called while already populating. Skipping.")
              return
         self._populating_details = True
         try:
             # --- Clear common fields ---
             self.name_input.clear()
             self.tags_input.clear()

             # --- Clear dynamic layouts ---
             # Use object names for clarity if set previously
             self.clear_layout(self.item_attributes_layout)
             self.clear_layout(self.base_abilities_layout)
             self.clear_layout(self.recycling_parts_layout)
             self.clear_layout(self.variants_layout)
             self.clear_layout(self.properties_layout) # For abilities

             # --- Hide specific sections ---
             self.set_item_specific_visibility(False)
             self.set_ability_specific_visibility(False)

             # --- Reset selection state ---
             self.current_selection_name = None
             self.current_selection_type = None
             self.current_selection_element = None
             self.current_selection_filepath = None

             # Update window title (removes filename and markers)
             self.update_window_title()
             logging.debug("Details pane cleared and selection reset.")

         finally:
             self._populating_details = False # Re-enable signals


    def _attach_completer(self, line_edit, model, field_context_name="Unknown Field"):
        """Creates and attaches a QCompleter to a QLineEdit."""
        if not isinstance(line_edit, QLineEdit):
            logging.warning(f"Cannot attach completer: Provided widget is not a QLineEdit ({type(line_edit)}). Context: {field_context_name}")
            return
        if not isinstance(model, QStringListModel):
            logging.warning(f"Cannot attach completer: Provided model is not a QStringListModel ({type(model)}). Context: {field_context_name}")
            return
        if model.rowCount() == 0:
            # logging.debug(f"Skipping completer for '{field_context_name}': Model is empty.")
            # Still remove any existing completer in case the model was emptied
            line_edit.setCompleter(None)
            return

        # logging.debug(f"Attaching completer to '{field_context_name}' (LineEdit: {line_edit.objectName()}) with {model.rowCount()} items.")
        completer = QCompleter(model, line_edit) # Parent is the line edit
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains) # Contains matching
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion) # Standard popup
        line_edit.setCompleter(completer)
        # logging.debug(f"Completer attached successfully for '{field_context_name}'.")


    def clear_data(self):
        """Clears all loaded XML data, maps, sets, models, and UI lists."""
        logging.info("Clearing all loaded data...")
        # Block signals during this major reset
        self._populating_details = True
        try:
            # 1. Clear main data structures
            self.loaded_files.clear()
            self.abilities_map.clear()
            self.items_map.clear()
            self.modified_files.clear()

            # 2. Clear all autocompletion data sets
            self.all_property_names.clear()
            self.all_item_attribute_names.clear()
            # ... (clear all other self.all_* sets) ...
            self.all_anim_actions.clear()
            logging.debug("Cleared data sets.")

            # 3. Clear models (setStringList([]) is efficient)
            self.item_attribute_name_model.setStringList([])
            self.variant_attribute_name_model.setStringList([])
            # ... (clear all other models) ...
            self.anim_action_model.setStringList([])
            logging.debug("Cleared completer models.")

            # 4. Clear UI lists
            self.ability_list.clear()
            self.item_list.clear()
            logging.debug("Cleared UI lists.")

            # 5. Clear the details pane (which also resets selection)
            self.clear_details_pane() # Call the dedicated method

            # 6. Reset config related variable (optional, maybe keep last folder?)
            # self.last_folder = "" # Uncomment if you want 'clear data' to forget the folder

            # 7. Update window title
            self.update_window_title() # Should already be updated by clear_details_pane

            logging.info("All data cleared.")
        finally:
            self._populating_details = False

    def populate_lists(self):
        """Populates the Ability and Item lists in the left pane."""
        logging.info("Populating UI lists (Abilities/Items)...")
        # Block selection signals while populating lists
        self.ability_list.blockSignals(True)
        self.item_list.blockSignals(True)
        try:
            self.ability_list.clear()
            self.item_list.clear()

            ability_names = sorted(self.abilities_map.keys())
            item_names = sorted(self.items_map.keys())

            for name in ability_names:
                self.ability_list.addItem(QListWidgetItem(name))
            for name in item_names:
                self.item_list.addItem(QListWidgetItem(name))

            logging.info(f"Populated lists: {len(ability_names)} abilities, {len(item_names)} items.")
        finally:
            self.ability_list.blockSignals(False)
            self.item_list.blockSignals(False)

    def list_item_selected(self, current_item, item_type):
        """Slot called when an item in the Ability or Item list is selected."""
        if self._populating_details: # Prevent selection changes during population
            # logging.debug("List selection change ignored while populating details.")
            return
        if not current_item:
            logging.debug("List selection cleared.")
            self.clear_details_pane()
            return

        name = current_item.text()
        # Avoid unnecessary reloads if the same item is clicked again
        if name == self.current_selection_name and item_type == self.current_selection_type:
            # logging.debug(f"Selection unchanged: {item_type} '{name}'. Skipping reload.")
            return

        logging.info(f"Selected {item_type}: '{name}'")
        self.populate_details(name, item_type)


    def populate_details(self, name, item_type):
        """Populates the right pane with details for the selected item or ability."""
        logging.debug(f"Populating details for {item_type} '{name}'...")
        if self._populating_details:
            logging.warning("populate_details called while already populating. Skipping.")
            return

        self.clear_details_pane() # Clear existing details first
        self._populating_details = True # Prevent signals during this population phase
        try:
            data_map = self.abilities_map if item_type == TAG_ABILITY else self.items_map
            if name not in data_map:
                logging.error(f"Cannot populate details: {item_type} '{name}' not found in map.")
                QMessageBox.critical(self, "Internal Error", f"Data for '{name}' could not be found.")
                return # Exit early

            item_data = data_map[name]
            element = item_data['element']
            file_path = item_data['filepath']

            # --- Update Current Selection State ---
            self.current_selection_name = name
            self.current_selection_type = item_type
            self.current_selection_element = element
            self.current_selection_filepath = file_path
            logging.debug(f"Current selection set: {item_type} '{name}' from file '{os.path.basename(file_path)}'")

            # --- Populate Common Fields ---
            self.name_input.setText(name)
            tags_element = element.find(TAG_TAGS)
            tags_text = tags_element.text.strip() if tags_element is not None and tags_element.text else ""
            self.tags_input.setText(tags_text)
            # Ensure completer is attached for tags (might have been cleared)
            self._attach_completer(self.tags_input, self.tag_model, "Tags")


            # --- Populate Specific Sections ---
            if item_type == TAG_ITEM:
                logging.debug("Populating item-specific sections...")
                self._populate_item_details(element, file_path)
                self.set_item_specific_visibility(True)
                self.set_ability_specific_visibility(False)
            elif item_type == TAG_ABILITY:
                logging.debug("Populating ability-specific sections...")
                self._populate_ability_details(element, file_path)
                self.set_item_specific_visibility(False)
                self.set_ability_specific_visibility(True)
            else:
                 logging.error(f"Unknown item_type '{item_type}' in populate_details.")

            self.update_window_title()
            logging.debug(f"Finished populating details for {item_type} '{name}'.")

        except Exception as e:
             logging.error(f"Error populating details for {item_type} '{name}': {e}", exc_info=True)
             QMessageBox.critical(self, "Population Error", f"An error occurred while displaying details for '{name}':\n{e}")
        finally:
             self._populating_details = False # Re-enable signals


    def _populate_item_details(self, element, file_path):
        """Populates the right pane sections specific to Items."""
        # Called by populate_details, _populating_details flag is already True
        self._populate_item_attributes(element)
        self._populate_item_list_section(element, TAG_BASE_ABILITIES, TAG_ABILITY_REF, self.base_abilities_layout, self.add_base_ability_widget)
        self._populate_item_list_section(element, TAG_RECYCLING_PARTS, TAG_PARTS, self.recycling_parts_layout, self.add_recycling_part_widget)
        self._populate_item_list_section(element, TAG_VARIANTS, TAG_VARIANT, self.variants_layout, self.add_variant_widget)

    def _populate_ability_details(self, element, file_path):
        """Populates the right pane sections specific to Abilities (Properties)."""
        # Called by populate_details, _populating_details flag is already True
        logging.debug(f"Populating Ability properties for: {element.get('name')}")
        self.clear_layout(self.properties_layout) # Clear previous properties first
        prop_count = 0
        for child in element:
            # Display direct children that are elements and *not* known structural tags
            if ET.iselement(child) and child.tag not in self.KNOWN_ABILITY_CHILD_TAGS:
                try:
                    prop_widget = PropertyWidget(child, file_path, self)
                    self.properties_layout.addWidget(prop_widget)
                    prop_count += 1
                except Exception as e:
                    logging.error(f"Failed to create PropertyWidget for child <{child.tag}> of ability '{element.get('name')}': {e}", exc_info=True)
        logging.debug(f"Added {prop_count} property widgets for ability '{element.get('name')}'.")

    def _populate_item_attributes(self, element):
        """Populates the Item Attributes grid layout."""
        logging.debug("Populating Item Attributes section...")
        self.clear_layout(self.item_attributes_layout)
        row = 0
        # Sort attributes alphabetically for consistent order
        for key, value in sorted(element.attrib.items()):
             if key == 'name': continue # Skip name attribute, shown in common field

             logging.debug(f"  Adding attribute widget: {key} = '{value}'")
             attr_label = QLabel(f"{key}:")
             attr_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
             attr_input = QLineEdit(value)
             attr_input.setObjectName(f"input_item_attr_{key}") # Object name for debugging/styling

             # Add widgets to layout FIRST
             self.item_attributes_layout.addWidget(attr_label, row, 0)
             self.item_attributes_layout.addWidget(attr_input, row, 1)

             # Attach completer AFTER adding to layout
             self._attach_completer_for_item_attribute(key, attr_input)

             # Connect signal
             # Use lambda with default arguments to capture current key and input
             attr_input.editingFinished.connect(
                 lambda k=key, i=attr_input: self.item_attribute_changed(k, i.text())
             )
             row += 1

        # Add the "+ Item Attribute" button at the end
        add_item_attr_button = QPushButton(QIcon.fromTheme("list-add"), "Add Item Attribute")
        add_item_attr_button.setToolTip("Add a new attribute to this item")
        add_item_attr_button.clicked.connect(self.add_item_attribute)
        self.item_attributes_layout.addWidget(add_item_attr_button, row, 0, 1, 2, Qt.AlignmentFlag.AlignLeft) # Span 2 cols, align left
        logging.debug("Finished Item Attributes section.")


    def _attach_completer_for_item_attribute(self, key, line_edit):
         """Attaches the appropriate completer based on the item attribute key."""
         context_name = f"Item Attribute '{key}'"
         if key == 'category': self._attach_completer(line_edit, self.item_category_model, context_name)
         elif key == 'ability_mode': self._attach_completer(line_edit, self.ability_mode_model, context_name)
         elif key == 'equip_template': self._attach_completer(line_edit, self.equip_template_model, context_name)
         elif key == 'equip_slot': self._attach_completer(line_edit, self.equip_slot_model, context_name)
         elif key == 'hold_slot': self._attach_completer(line_edit, self.hold_slot_model, context_name)
         elif key == 'hand': self._attach_completer(line_edit, self.hand_model, context_name)
         elif key == 'sound_identification': self._attach_completer(line_edit, self.sound_id_model, context_name)
         elif key in ['draw_event', 'holster_event']: self._attach_completer(line_edit, self.event_model, context_name)
         elif key in ['draw_act', 'draw_deact', 'holster_act', 'holster_deact']: self._attach_completer(line_edit, self.anim_action_model, context_name)
         elif key == 'enhancement_slots': self._attach_completer(line_edit, self.enhancement_slots_model, context_name)
         elif key in ['weapon', 'lethal', 'quest', 'indestructible']: self._attach_completer(line_edit, self.boolean_value_model, context_name) # Add more booleans
         elif key.startswith('localisation_key'): self._attach_completer(line_edit, self.localisation_key_model, context_name)
         elif key == 'icon_path': self._attach_completer(line_edit, self.icon_path_model, context_name)
         # Add more specific completers as needed
         # else: No specific completer for this attribute key

    def _populate_item_list_section(self, parent_element, section_tag, child_tag, layout, add_widget_func):
        """Generic function to populate list-like sections (Base Abilities, Recycling, Variants)."""
        logging.debug(f"Populating item section: <{section_tag}>")
        self.clear_layout(layout)
        section_node = parent_element.find(section_tag)
        count = 0
        if section_node is not None:
            for child_element in section_node.findall(child_tag):
                if ET.iselement(child_element): # Ensure it's an element
                    try:
                        add_widget_func(child_element) # Call the specific widget creation function
                        count += 1
                    except Exception as e:
                        logging.error(f"Failed to add widget for <{child_tag}> in <{section_tag}>: {e}", exc_info=True)
        # else: No section node found
        logging.debug(f"Finished populating <{section_tag}> section. Added {count} widgets.")


    # --- Widget Add/Remove Helpers for Item Sections ---

    def add_base_ability_widget(self, ab_element):
        """Adds a widget row for a <base_abilities> -> <a> element."""
        # Ensure _populating_details is checked by the caller (_populate_item_list_section)
        ability_text = ab_element.text.strip() if ab_element.text else ""
        logging.debug(f"  Adding Base Ability widget for: '{ability_text}'")

        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        ab_input = QLineEdit(ability_text)
        ab_input.setPlaceholderText("Ability Name")
        ab_input.setObjectName(f"input_base_ability_{id(ab_element)}") # Use id for uniqueness

        remove_button = QPushButton("X")
        remove_button.setFixedWidth(30)
        remove_button.setToolTip("Remove this base ability reference")

        # Add widgets to layout FIRST
        layout.addWidget(ab_input)
        layout.addWidget(remove_button)
        self.base_abilities_layout.addWidget(widget) # Add row widget to the section layout

        # Attach completer AFTER adding to layout
        self._attach_completer(ab_input, self.ability_name_model, "Base Ability Name")

        # Connect signals
        # Disconnect first to prevent duplicates if re-populating
        try: ab_input.editingFinished.disconnect()
        except RuntimeError: pass
        ab_input.editingFinished.connect(lambda elem=ab_element, inp=ab_input: self.base_ability_text_changed(elem, inp.text()))

        try: remove_button.clicked.disconnect()
        except RuntimeError: pass
        remove_button.clicked.connect(lambda w=widget, elem=ab_element: self.remove_list_widget(
            w, elem, TAG_BASE_ABILITIES, self.base_abilities_layout, "Base Ability"
        ))

    def add_recycling_part_widget(self, part_element):
        """Adds a widget row for a <recycling_parts> -> <parts> element."""
        count_value = part_element.get('count', '1') # Default to 1 if count missing
        part_text = part_element.text.strip() if part_element.text else ""
        logging.debug(f"  Adding Recycling Part widget: Count='{count_value}', Name='{part_text}'")

        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        label_count = QLabel("Count:")
        count_input = QLineEdit(count_value)
        count_input.setFixedWidth(50)
        count_input.setPlaceholderText("Qty")
        count_input.setObjectName(f"input_recycling_count_{id(part_element)}")

        label_name = QLabel(" Name:") # Add space for visual separation
        name_input = QLineEdit(part_text)
        name_input.setPlaceholderText("Part Item Name")
        name_input.setObjectName(f"input_recycling_name_{id(part_element)}")

        remove_button = QPushButton("X")
        remove_button.setFixedWidth(30)
        remove_button.setToolTip("Remove this recycling part")

        # Add widgets to layout FIRST
        layout.addWidget(label_count)
        layout.addWidget(count_input)
        layout.addWidget(label_name)
        layout.addWidget(name_input)
        layout.addStretch(1) # Push button to the right
        layout.addWidget(remove_button)
        self.recycling_parts_layout.addWidget(widget)

        # Attach completer to name input AFTER adding to layout
        self._attach_completer(name_input, self.item_name_model, "Recycling Part Name") # Parts are items

        # Connect signals
        try: count_input.editingFinished.disconnect()
        except RuntimeError: pass
        count_input.editingFinished.connect(lambda elem=part_element, inp=count_input: self.part_attribute_changed(elem, 'count', inp.text()))

        try: name_input.editingFinished.disconnect()
        except RuntimeError: pass
        name_input.editingFinished.connect(lambda elem=part_element, inp=name_input: self.part_text_changed(elem, inp.text()))

        try: remove_button.clicked.disconnect()
        except RuntimeError: pass
        remove_button.clicked.connect(lambda w=widget, elem=part_element: self.remove_list_widget(
             w, elem, TAG_RECYCLING_PARTS, self.recycling_parts_layout, "Recycling Part"
        ))

    def add_variant_widget(self, var_element):
        """Adds a widget structure for a <variants> -> <variant> element."""
        logging.debug(f"  Adding Variant widget for variant with attrs: {var_element.attrib}")

        # Main container for the whole variant row (allows complex internal layout)
        variant_row_widget = QWidget()
        variant_row_widget.setObjectName(f"VariantRow_{id(var_element)}")
        # Use a border for visual separation of variants
        variant_row_widget.setStyleSheet("QWidget#VariantRow_" + str(id(var_element)) + " { border: 1px solid gray; margin-bottom: 5px; }")

        # Main layout: Details on the left, Remove button on the right
        row_layout = QHBoxLayout(variant_row_widget)
        row_layout.setContentsMargins(5, 5, 5, 5)
        row_layout.setSpacing(10)

        # Left side layout (vertical: attributes, then nested items)
        details_layout = QVBoxLayout()
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(5)
        row_layout.addLayout(details_layout)

        # --- Variant Attributes ---
        attributes_layout = QGridLayout()
        attributes_layout.setObjectName(f"VariantAttributesLayout_{id(var_element)}")
        attributes_layout.setContentsMargins(0, 0, 0, 5)
        details_layout.addLayout(attributes_layout)
        attr_row = 0
        attribute_widgets = {} # Keep track if needed

        if var_element.attrib:
            for key, value in sorted(var_element.attrib.items()):
                attr_label = QLabel(f"{key}:")
                attr_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
                attr_input = QLineEdit(value)
                attr_input.setObjectName(f"input_variant_attr_{key}_{id(var_element)}")

                # Add widgets FIRST
                attributes_layout.addWidget(attr_label, attr_row, 0)
                attributes_layout.addWidget(attr_input, attr_row, 1)
                attribute_widgets[key] = attr_input

                # Attach completer AFTER
                self._attach_completer_for_variant_attribute(key, attr_input)

                # Connect signal
                try: attr_input.editingFinished.disconnect()
                except RuntimeError: pass
                attr_input.editingFinished.connect(
                    lambda k=key, i=attr_input, elem=var_element: self.variant_attribute_changed(elem, k, i.text()))
                attr_row += 1
        else:
            # Add a placeholder label if no attributes initially
             no_attr_label = QLabel("<i>No attributes defined for this variant.</i>")
             attributes_layout.addWidget(no_attr_label, attr_row, 0, 1, 2)
             attr_row +=1

        # Button to add attributes to *this* variant
        add_variant_attr_button = QPushButton(QIcon.fromTheme("list-add"), "+ Variant Attribute")
        add_variant_attr_button.setToolTip("Add a new attribute to this specific variant")
        try: add_variant_attr_button.clicked.disconnect()
        except RuntimeError: pass
        # Pass necessary context to the add function
        add_variant_attr_button.clicked.connect(
            lambda elem=var_element, layout=attributes_layout, button=add_variant_attr_button:
            self.add_variant_attribute(elem, layout, button) # Pass layout and button itself
        )
        # Place the button below existing attributes
        attributes_layout.addWidget(add_variant_attr_button, attr_row, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
        # --- End Variant Attributes ---


        # --- Nested Elements (e.g., <item>, <ability>) ---
        nested_container = QWidget() # Container for nested items + add button
        nested_container_layout = QVBoxLayout(nested_container)
        nested_container_layout.setContentsMargins(15, 5, 0, 5) # Indent nested items
        nested_container_layout.setSpacing(3)
        details_layout.addWidget(nested_container) # Add nested container to the main details layout

        nested_items_layout = QVBoxLayout() # Layout *just* for the nested item widgets
        nested_items_layout.setObjectName(f"NestedItemsLayout_{id(var_element)}")
        nested_items_layout.setContentsMargins(0,0,0,0)
        nested_items_layout.setSpacing(1)
        nested_container_layout.addLayout(nested_items_layout) # Add item layout to container

        nested_element_found = False
        for child_node in var_element: # Iterate through all children
            if ET.iselement(child_node): # Process only elements
                nested_element_found = True
                self.add_nested_variant_item_widget(child_node, var_element, nested_items_layout)
            # else: Ignore comments, PIs etc.

        if not nested_element_found:
             no_nested_label = QLabel("<i>No nested elements (e.g., <item>, <ability>) found.</i>")
             nested_items_layout.addWidget(no_nested_label)


        # Button to add nested items (place inside the nested container)
        add_nested_item_button = QPushButton(QIcon.fromTheme("list-add"), "+ Nested Element")
        add_nested_item_button.setToolTip("Add a new element (e.g., <item>, <ability>) inside this variant")
        try: add_nested_item_button.clicked.disconnect()
        except RuntimeError: pass
        # nested_items_layout is the target layout for *new* item widgets
        add_nested_item_button.clicked.connect(
            lambda v_elem=var_element, layout=nested_items_layout: self.add_nested_variant_item(v_elem, layout)
        )
        nested_container_layout.addWidget(add_nested_item_button, alignment=Qt.AlignmentFlag.AlignLeft)
        # --- End Nested Elements ---


        # --- Remove Button for the whole variant ---
        remove_button = QPushButton("X")
        remove_button.setFixedWidth(30)
        remove_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        remove_button.setToolTip(f"Remove this entire variant")
        try: remove_button.clicked.disconnect()
        except RuntimeError: pass
        # Pass the main row widget to remove
        remove_button.clicked.connect(lambda w=variant_row_widget, elem=var_element: self.remove_list_widget(
            w, elem, TAG_VARIANTS, self.variants_layout, "Variant"
        ))
        # Add remove button to the main horizontal layout, aligned top-right
        row_layout.addWidget(remove_button, 0, Qt.AlignmentFlag.AlignTop) # Add with stretch factor 0


        # Add the complete variant row widget to the main variants section layout
        self.variants_layout.addWidget(variant_row_widget)


    def _attach_completer_for_variant_attribute(self, key, line_edit):
         """Attaches the appropriate completer based on the variant attribute key."""
         context_name = f"Variant Attribute '{key}'"
         # Add known variant attributes here
         if key == 'category': self._attach_completer(line_edit, self.item_category_model, context_name)
         elif key == 'equip_template': self._attach_completer(line_edit, self.equip_template_model, context_name)
         elif key == 'required_build': self._attach_completer(line_edit, self.boolean_value_model, context_name) # Example
         # Add more specific completers as needed


    def add_nested_variant_item_widget(self, child_element, variant_element, target_layout):
        """Adds a widget for a nested element within a <variant> (e.g., <item>, <ability>)."""
        # Caller should ensure child_element is valid
        child_tag = child_element.tag
        child_text = child_element.text.strip() if child_element.text else ""
        logging.debug(f"    Adding Nested Variant Item widget: Tag='{child_tag}', Text='{child_text}'")

        nested_widget = QWidget()
        nested_layout = QHBoxLayout(nested_widget)
        nested_layout.setContentsMargins(0, 0, 0, 0)
        nested_layout.setSpacing(5)

        # Simple label for the tag
        tag_label = QLabel(f"{child_tag}:")
        tag_label.setFixedWidth(50) # Adjust width as needed
        tag_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        nested_layout.addWidget(tag_label)

        text_input = QLineEdit(child_text)
        text_input.setObjectName(f"input_nested_{child_tag}_{id(child_element)}")

        nested_layout.addWidget(text_input) # Add input FIRST

        # Attach completer AFTER adding to layout
        context_name = f"Nested Variant Element '{child_tag}'"
        tag_lower = child_tag.lower()
        if tag_lower == TAG_ITEM:
            self._attach_completer(text_input, self.item_name_model, context_name)
        elif tag_lower == TAG_ABILITY:
             self._attach_completer(text_input, self.ability_name_model, context_name)
        # Add other potential nested tags here
        else:
             logging.debug(f"No specific completer defined for nested tag '{child_tag}'.")

        remove_nested_button = QPushButton("x") # Smaller button
        remove_nested_button.setFixedWidth(25)
        remove_nested_button.setToolTip(f"Remove this <{child_tag}> element")
        nested_layout.addWidget(remove_nested_button) # Add button

        target_layout.addWidget(nested_widget) # Add the whole row to the passed layout

        # Connect signals
        try: text_input.editingFinished.disconnect()
        except RuntimeError: pass
        text_input.editingFinished.connect(lambda elem=child_element, inp=text_input: self.nested_variant_item_text_changed(elem, inp.text()))

        try: remove_nested_button.clicked.disconnect()
        except RuntimeError: pass
        remove_nested_button.clicked.connect(lambda w=nested_widget, elem=child_element, p_elem=variant_element: self.remove_nested_variant_item(w, elem, p_elem))


    def remove_list_widget(self, widget_to_remove, element_to_remove, parent_tag_constant, layout, item_description="item"):
        """Removes a widget and its corresponding XML element from a list section (e.g., base ability, part, variant)."""
        if self._populating_details:
            logging.debug(f"Remove {item_description} skipped: Populating details.")
            return
        if not self.current_selection_element:
            logging.warning(f"Remove {item_description} skipped: No current element selected.")
            return

        parent_node = self.current_selection_element.find(parent_tag_constant)
        if parent_node is None:
            # This might happen if the parent node (e.g., <base_abilities>) was empty and removed previously.
            logging.warning(f"Cannot remove {item_description} <{element_to_remove.tag}>: Parent node <{parent_tag_constant}> not found.")
            # If the parent node is gone, the element should be gone too, just remove the widget.
            widget_to_remove.deleteLater()
            logging.debug("Removed orphan widget as parent node was missing.")
            return

        # Confirmation (optional, uncomment if desired)
        # elem_repr = element_to_remove.get('name', element_to_remove.text if element_to_remove.text else f'<{element_to_remove.tag}>')
        # confirm = QMessageBox.question(self, f"Remove {item_description}", f"Are you sure you want to remove this {item_description}:\n'{elem_repr}'?")
        # if confirm != QMessageBox.StandardButton.Yes:
        #     return

        try:
            logging.info(f"Removing {item_description} element <{element_to_remove.tag}> from <{parent_tag_constant}>")
            parent_node.remove(element_to_remove)
            self.mark_file_modified(self.current_selection_filepath)
            widget_to_remove.deleteLater() # Remove the UI widget
            logging.debug(f"Successfully removed {item_description} and its widget.")

            # Optional: Remove the parent node (e.g., <base_abilities>) if it becomes empty
            # if not list(parent_node) and not parent_node.attrib and not parent_node.text:
            #     grandparent = self.get_parent_element(parent_node, self.current_selection_filepath)
            #     if grandparent is not None:
            #         logging.info(f"Removing empty parent node <{parent_tag_constant}>")
            #         grandparent.remove(parent_node)
            #         # No need to mark modified again

        except ValueError:
            logging.error(f"Element <{element_to_remove.tag}> not found in <{parent_tag_constant}> during removal (ValueError).", exc_info=True)
            # Element might already be removed, still delete the widget
            widget_to_remove.deleteLater()
        except Exception as e:
            logging.error(f"Error removing {item_description} list widget: {e}", exc_info=True)
            QMessageBox.critical(self, "Removal Error", f"An error occurred while removing the {item_description}:\n{e}")


    # --- Editing Actions Handlers (Slots) ---

    def tags_changed(self):
        """Handles changes in the main Tags input field."""
        if self._populating_details or not self.current_selection_element: return
        new_tags_text = self.tags_input.text().strip()
        tags_element = self.current_selection_element.find(TAG_TAGS)
        current_text = tags_element.text.strip() if tags_element is not None and tags_element.text else ""

        if new_tags_text == current_text: return # No change

        if tags_element is None:
            if new_tags_text: # Only add element if there's text
                logging.info(f"Adding <{TAG_TAGS}> element with text: {new_tags_text}")
                tags_element = ET.SubElement(self.current_selection_element, TAG_TAGS)
                tags_element.text = new_tags_text
                self.mark_file_modified(self.current_selection_filepath)
        elif new_tags_text: # Element exists, update text
            logging.info(f"Updating <{TAG_TAGS}> text from '{current_text}' to '{new_tags_text}'")
            tags_element.text = new_tags_text
            self.mark_file_modified(self.current_selection_filepath)
        else: # Element exists, but new text is empty -> remove element
            logging.info(f"Removing empty <{TAG_TAGS}> element.")
            try:
                self.current_selection_element.remove(tags_element)
                self.mark_file_modified(self.current_selection_filepath)
            except ValueError:
                 logging.warning(f"Could not remove <{TAG_TAGS}> element, possibly already removed.")

        # Update tag completer model if new tags were added
        added_tags = {t.strip() for t in new_tags_text.split(',') if t.strip() and t.strip() not in self.all_tags}
        if added_tags:
            logging.debug(f"Adding new tags to completer model: {added_tags}")
            self.all_tags.update(added_tags)
            self._update_single_completer_model(self.tag_model, self.all_tags, "tag")

    def item_attribute_changed(self, attr_name, new_value):
        """Handles changes in the main Item Attribute QLineEdits."""
        if self._populating_details or not self.current_selection_element or self.current_selection_type != TAG_ITEM: return
        old_value = self.current_selection_element.get(attr_name)
        # Normalize empty strings vs None
        old_value_norm = old_value if old_value is not None else ""
        new_value_norm = new_value.strip()

        if old_value_norm != new_value_norm:
            logging.info(f"Item attribute '{attr_name}' changed from '{old_value_norm}' to '{new_value_norm}' for '{self.current_selection_name}'")
            # Handle removal of attribute if value is empty? Decide policy.
            # For now, set empty string if cleared.
            # if not new_value_norm and attr_name in self.current_selection_element.attrib:
            #     del self.current_selection_element.attrib[attr_name]
            # else:
            self.current_selection_element.set(attr_name, new_value_norm)
            self.mark_file_modified(self.current_selection_filepath)
            # Optional: Update relevant completer model if the value came from one (e.g., category)
            self._update_completer_set_and_model_from_value(attr_name, new_value_norm)


    def base_ability_text_changed(self, ab_element, new_text):
        """Handles text change in a Base Ability input."""
        if self._populating_details: return
        new_text_stripped = new_text.strip()
        current_text = ab_element.text.strip() if ab_element.text else ""
        if current_text != new_text_stripped:
            logging.info(f"Base ability text changed from '{current_text}' to '{new_text_stripped}'")
            ab_element.text = new_text_stripped
            self.mark_file_modified(self.current_selection_filepath)
            # Update ability name model if it's a new name
            if new_text_stripped and new_text_stripped not in self.all_ability_names:
                self.all_ability_names.add(new_text_stripped)
                self._update_single_completer_model(self.ability_name_model, self.all_ability_names, "ability_name")


    def part_attribute_changed(self, part_element, attr_name, new_value):
        """Handles attribute change (e.g., 'count') for a Recycling Part."""
        if self._populating_details: return
        new_value_stripped = new_value.strip()
        # Add validation? Ensure count is numeric?
        # try:
        #     int(new_value_stripped)
        # except ValueError:
        #     QMessageBox.warning(self, "Invalid Input", f"Value for '{attr_name}' must be an integer.")
        #     # Revert widget text? Find the widget... complex. Better to just log.
        #     logging.warning(f"Invalid non-integer value '{new_value_stripped}' entered for recycling part attribute '{attr_name}'.")
        #     return # Or allow saving non-numeric? For now, allow.

        old_value = part_element.get(attr_name)
        if old_value != new_value_stripped:
            logging.info(f"Recycling part attribute '{attr_name}' changed from '{old_value}' to '{new_value_stripped}'")
            part_element.set(attr_name, new_value_stripped)
            self.mark_file_modified(self.current_selection_filepath)

    def part_text_changed(self, part_element, new_text):
        """Handles text change (item name) for a Recycling Part."""
        if self._populating_details: return
        new_text_stripped = new_text.strip()
        current_text = part_element.text.strip() if part_element.text else ""
        if current_text != new_text_stripped:
            logging.info(f"Recycling part name changed from '{current_text}' to '{new_text_stripped}'")
            part_element.text = new_text_stripped
            self.mark_file_modified(self.current_selection_filepath)
            # Update item name model if it's a new name
            if new_text_stripped and new_text_stripped not in self.all_item_names:
                self.all_item_names.add(new_text_stripped)
                self._update_single_completer_model(self.item_name_model, self.all_item_names, "item_name")
            # Also update recycling part name model
            if new_text_stripped and new_text_stripped not in self.all_recycling_part_names:
                self.all_recycling_part_names.add(new_text_stripped)
                self._update_single_completer_model(self.recycling_part_name_model, self.all_recycling_part_names, "recycling_part_name")


    def variant_attribute_changed(self, var_element, attr_name, new_value):
        """Handles attribute changes for a Variant element."""
        if self._populating_details: return
        new_value_stripped = new_value.strip()
        old_value = var_element.get(attr_name)
        old_value_norm = old_value if old_value is not None else ""

        if old_value_norm != new_value_stripped:
             logging.info(f"Variant attribute '{attr_name}' changed from '{old_value_norm}' to '{new_value_stripped}'")
             var_element.set(attr_name, new_value_stripped)
             self.mark_file_modified(self.current_selection_filepath)
             # Optional: Update relevant completer model if the value came from one
             self._update_completer_set_and_model_from_value(attr_name, new_value_stripped)


    def nested_variant_item_text_changed(self, child_element, new_text):
        """Handles text changes for nested items/abilities within a Variant."""
        if self._populating_details: return
        new_text_stripped = new_text.strip()
        current_text = child_element.text.strip() if child_element.text else ""
        if current_text != new_text_stripped:
            logging.info(f"Nested variant element <{child_element.tag}> text changed from '{current_text}' to '{new_text_stripped}'")
            child_element.text = new_text_stripped
            self.mark_file_modified(self.current_selection_filepath)
            # Update relevant name model if it's a new name
            tag_lower = child_element.tag.lower()
            if tag_lower == TAG_ITEM and new_text_stripped and new_text_stripped not in self.all_item_names:
                 self.all_item_names.add(new_text_stripped)
                 self._update_single_completer_model(self.item_name_model, self.all_item_names, "item_name")
            elif tag_lower == TAG_ABILITY and new_text_stripped and new_text_stripped not in self.all_ability_names:
                 self.all_ability_names.add(new_text_stripped)
                 self._update_single_completer_model(self.ability_name_model, self.all_ability_names, "ability_name")


    def _update_completer_set_and_model_from_value(self, attr_name, new_value):
         """Checks if an attribute corresponds to a known completer set and updates if value is new."""
         if not new_value: return # Don't add empty strings

         target_set = None
         target_model = None
         model_name = ""

         if attr_name == 'category':
             target_set, target_model, model_name = self.all_item_categories, self.item_category_model, "item_category"
         elif attr_name == 'ability_mode':
              target_set, target_model, model_name = self.all_ability_modes, self.ability_mode_model, "ability_mode"
         elif attr_name == 'equip_template':
              target_set, target_model, model_name = self.all_equip_templates, self.equip_template_model, "equip_template"
         # Add other attribute -> set/model mappings here...
         elif attr_name == 'equip_slot':
              target_set, target_model, model_name = self.all_equip_slots, self.equip_slot_model, "equip_slot"
         elif attr_name == 'hold_slot':
              target_set, target_model, model_name = self.all_hold_slots, self.hold_slot_model, "hold_slot"
         # ... etc.

         if target_set is not None and new_value not in target_set:
              logging.debug(f"Adding new value '{new_value}' to set/model for '{model_name}' (from attribute '{attr_name}')")
              target_set.add(new_value)
              self._update_single_completer_model(target_model, target_set, model_name)


    # --- Add Buttons for Sections ---

    def _find_or_create_section_node(self, parent_element, section_tag):
        """Finds a direct child node or creates it if it doesn't exist."""
        node = parent_element.find(section_tag)
        if node is None:
             logging.info(f"Creating missing section node <{section_tag}> under <{parent_element.tag}>")
             node = ET.SubElement(parent_element, section_tag)
             # Mark modified? Assume caller handles it after adding child.
        return node

    def add_base_ability(self):
        """Adds a new, empty base ability reference to the item."""
        if self._populating_details or not self.current_selection_element or self.current_selection_type != TAG_ITEM: return
        logging.info("Adding new base ability reference...")
        parent_node = self._find_or_create_section_node(self.current_selection_element, TAG_BASE_ABILITIES)
        if parent_node is not None:
            new_child = ET.SubElement(parent_node, TAG_ABILITY_REF) # Creates <a></a>
            self.add_base_ability_widget(new_child) # Add the UI widget for it
            self.mark_file_modified(self.current_selection_filepath)
            logging.debug(f"Added new <{TAG_ABILITY_REF}> to <{TAG_BASE_ABILITIES}>")
            # Ensure the section is visible if it was hidden
            if not self.base_abilities_section.isVisible():
                 self.set_item_specific_visibility(True)
        else:
             logging.error("Failed to find or create <base_abilities> node.")


    def add_recycling_part(self):
        """Adds a new, default recycling part to the item."""
        if self._populating_details or not self.current_selection_element or self.current_selection_type != TAG_ITEM: return
        logging.info("Adding new recycling part...")
        parent_node = self._find_or_create_section_node(self.current_selection_element, TAG_RECYCLING_PARTS)
        if parent_node is not None:
            new_child = ET.SubElement(parent_node, TAG_PARTS)
            new_child.set('count', '1') # Default count
            new_child.text = "New_Part_Name" # Default placeholder text
            self.add_recycling_part_widget(new_child)
            self.mark_file_modified(self.current_selection_filepath)
            logging.debug(f"Added new <{TAG_PARTS}> to <{TAG_RECYCLING_PARTS}>")
            if not self.recycling_parts_section.isVisible():
                 self.set_item_specific_visibility(True)
        else:
             logging.error("Failed to find or create <recycling_parts> node.")

    def add_variant(self):
        """Adds a new, default variant to the item."""
        if self._populating_details or not self.current_selection_element or self.current_selection_type != TAG_ITEM: return
        logging.info("Adding new variant...")
        parent_node = self._find_or_create_section_node(self.current_selection_element, TAG_VARIANTS)
        if parent_node is not None:
            new_child = ET.SubElement(parent_node, TAG_VARIANT)
            # Add some default attributes to make it useful
            new_child.set('category', self.current_selection_element.get('category', 'DefaultCategory')) # Inherit category?
            new_child.set('equip_template', 'DefaultTemplate') # Add default template
            self.add_variant_widget(new_child)
            self.mark_file_modified(self.current_selection_filepath)
            logging.debug(f"Added new <{TAG_VARIANT}> to <{TAG_VARIANTS}>")
            if not self.variants_section.isVisible():
                 self.set_item_specific_visibility(True)
        else:
             logging.error("Failed to find or create <variants> node.")


    def add_item_attribute(self):
         """Adds a new attribute to the main <item> element."""
         if self._populating_details or not self.current_selection_element or self.current_selection_type != TAG_ITEM: return

         dialog = QInputDialog(self)
         dialog.setWindowTitle("Add Item Attribute")
         dialog.setLabelText("Name of the new attribute for <item>:")
         line_edit = dialog.findChild(QLineEdit)
         if line_edit:
             self._attach_completer(line_edit, self.item_attribute_name_model, "New Item Attribute Name")

         if dialog.exec() == QDialog.DialogCode.Accepted:
            attr_name = dialog.textValue().strip().replace(" ", "_")
            if not attr_name:
                QMessageBox.warning(self, "Error", "Attribute name cannot be empty.")
                return
            if attr_name in self.current_selection_element.attrib:
                QMessageBox.warning(self, "Error", f"Attribute '{attr_name}' already exists for this item.")
                return

            logging.info(f"Adding item attribute '{attr_name}' to '{self.current_selection_name}'")
            self.current_selection_element.set(attr_name, "") # Add with empty value
            self.mark_file_modified(self.current_selection_filepath)

            # Update completer model if it's a new attribute name
            if attr_name not in self.all_item_attribute_names:
                self.all_item_attribute_names.add(attr_name)
                self._update_single_completer_model(self.item_attribute_name_model, self.all_item_attribute_names, "item_attribute_name")

            # Refresh the item attributes section UI to show the new attribute
            # Set flag temporarily to avoid triggering change signals during refresh
            was_populating = self._populating_details
            self._populating_details = True
            try:
                self._populate_item_attributes(self.current_selection_element)
            finally:
                self._populating_details = was_populating

            logging.debug(f"Added item attribute '{attr_name}' and refreshed UI section.")


    def add_variant_attribute(self, variant_element, attributes_layout, add_button_widget):
         """Adds a new attribute to a specific <variant> element and updates its UI."""
         if self._populating_details: return

         dialog = QInputDialog(self)
         dialog.setWindowTitle("Add Variant Attribute")
         dialog.setLabelText("Name of the new attribute for <variant>:")
         line_edit = dialog.findChild(QLineEdit)
         if line_edit:
             # Suggest existing variant attribute names
             self._attach_completer(line_edit, self.variant_attribute_name_model, "New Variant Attribute Name")

         if dialog.exec() == QDialog.DialogCode.Accepted:
            attr_name = dialog.textValue().strip().replace(" ", "_")
            if not attr_name:
                QMessageBox.warning(self, "Error", "Attribute name cannot be empty.")
                return
            if attr_name in variant_element.attrib:
                QMessageBox.warning(self, "Error", f"Attribute '{attr_name}' already exists for this variant.")
                return

            logging.info(f"Adding variant attribute '{attr_name}'")
            variant_element.set(attr_name, "") # Add with empty value
            self.mark_file_modified(self.current_selection_filepath)

            # Update global completer model if it's a new variant attribute name globally
            if attr_name not in self.all_variant_attribute_names:
                self.all_variant_attribute_names.add(attr_name)
                self._update_single_completer_model(self.variant_attribute_name_model, self.all_variant_attribute_names, "variant_attribute_name")

            # --- Dynamically update the variant's attribute UI ---
            if not isinstance(attributes_layout, QGridLayout):
                 logging.error("Cannot add variant attribute widget: Invalid layout passed.")
                 return

            # Find the row of the add button
            button_index = attributes_layout.indexOf(add_button_widget)
            if button_index == -1:
                 logging.error("Cannot find Add Attribute button in variant layout to insert before.")
                 # Fallback: just append? Might mess up layout. Better to log error.
                 return

            button_row, _, _, _ = attributes_layout.getItemPosition(button_index)

            # Remove the button temporarily
            attributes_layout.takeAt(button_index)
            # add_button_widget.hide() # Hiding might be simpler than removing/re-adding

            # Add the new label and input in the button's previous row
            attr_label = QLabel(f"{attr_name}:")
            attr_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            attr_input = QLineEdit("")
            attr_input.setObjectName(f"input_variant_attr_{attr_name}_{id(variant_element)}")

            attributes_layout.addWidget(attr_label, button_row, 0)
            attributes_layout.addWidget(attr_input, button_row, 1)

            # Attach completer and connect signal for the new input
            self._attach_completer_for_variant_attribute(attr_name, attr_input)
            attr_input.editingFinished.connect(
                lambda k=attr_name, i=attr_input, elem=variant_element: self.variant_attribute_changed(elem, k, i.text()))

            # Re-add the button in the next row
            attributes_layout.addWidget(add_button_widget, button_row + 1, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
            # add_button_widget.show()

            logging.debug(f"Added attribute '{attr_name}' to variant UI layout.")
            # --- End UI Update ---


    def add_nested_variant_item(self, variant_element, nested_items_layout):
        """Adds a new nested element (like <item>) inside a <variant>."""
        if self._populating_details: return

        # --- Get Tag Name ---
        tag_dialog = QInputDialog(self)
        tag_dialog.setWindowTitle("Add Nested Element - Tag")
        tag_dialog.setLabelText("Tag name (e.g., 'item', 'ability'):")
        tag_dialog.setInputMode(QInputDialog.InputMode.TextInput)
        tag_dialog.setTextValue(TAG_ITEM) # Default to 'item'
        tag_line_edit = tag_dialog.findChild(QLineEdit)
        if tag_line_edit:
             self._attach_completer(tag_line_edit, self.variant_nested_tag_model, "New Nested Element Tag")

        if tag_dialog.exec() != QDialog.DialogCode.Accepted: return
        tag_name = tag_dialog.textValue().strip().replace(" ", "_")
        if not tag_name:
            QMessageBox.warning(self, "Error", "Tag name cannot be empty.")
            return

        # --- Get Text Value ---
        text_dialog = QInputDialog(self)
        text_dialog.setWindowTitle("Add Nested Element - Text")
        text_dialog.setLabelText(f"Text content for <{tag_name}>:")
        text_dialog.setInputMode(QInputDialog.InputMode.TextInput)
        text_line_edit = text_dialog.findChild(QLineEdit)
        if text_line_edit:
             context_name = f"Nested <{tag_name}> Text"
             tag_lower = tag_name.lower()
             if tag_lower == TAG_ITEM: self._attach_completer(text_line_edit, self.item_name_model, context_name)
             elif tag_lower == TAG_ABILITY: self._attach_completer(text_line_edit, self.ability_name_model, context_name)
             # Add others if needed

        if text_dialog.exec() != QDialog.DialogCode.Accepted: return
        text_value = text_dialog.textValue().strip() # Allow empty text? Yes.

        # --- Add to XML and UI ---
        logging.info(f"Adding nested element <{tag_name}> with text '{text_value}' to variant.")
        new_child = ET.SubElement(variant_element, tag_name)
        new_child.text = text_value
        self.mark_file_modified(self.current_selection_filepath)

        # Add UI widget for the new element
        self.add_nested_variant_item_widget(new_child, variant_element, nested_items_layout)

        # Update model for nested tags if it's a new tag type
        if tag_name not in self.all_variant_nested_tags:
             self.all_variant_nested_tags.add(tag_name)
             self._update_single_completer_model(self.variant_nested_tag_model, self.all_variant_nested_tags, "variant_nested_tag")

        logging.debug(f"Added nested element <{tag_name}> to variant and UI.")


    def remove_nested_variant_item(self, widget_to_remove, element_to_remove, parent_variant_element):
        """Removes a nested element (e.g., <item>) from within a <variant>."""
        if self._populating_details: return
        logging.info(f"Removing nested element <{element_to_remove.tag}> from variant.")
        try:
            parent_variant_element.remove(element_to_remove)
            self.mark_file_modified(self.current_selection_filepath)
            widget_to_remove.deleteLater()
            logging.debug("Removed nested element and widget.")
        except ValueError:
            logging.error(f"Element <{element_to_remove.tag}> not found in parent variant during removal (ValueError).", exc_info=True)
            widget_to_remove.deleteLater() # Remove widget anyway
        except Exception as e:
            logging.error(f"Error removing nested variant item widget: {e}", exc_info=True)
            QMessageBox.critical(self, "Removal Error", f"An error occurred removing the nested <{element_to_remove.tag}> element:\n{e}")

    def add_property(self): # For Abilities
        """Adds a new generic property to the currently selected Ability."""
        if self._populating_details: return
        if not self.current_selection_element:
            QMessageBox.warning(self, "Action Failed", "Please select an Ability first.")
            return
        if self.current_selection_type != TAG_ABILITY:
            QMessageBox.information(self, "Information", "This option is only available for Abilities.")
            return

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Add Ability Property")
        dialog.setLabelText("Enter the name (tag) of the new property (e.g., 'stamina_regen'):")
        dialog.setInputMode(QInputDialog.InputMode.TextInput)
        line_edit = dialog.findChild(QLineEdit)
        if line_edit:
            self._attach_completer(line_edit, self.property_name_model, "New Property Name")

        if dialog.exec() == QDialog.DialogCode.Accepted:
            prop_name = dialog.textValue().strip().replace(" ", "_") # Basic cleanup
            if not prop_name:
                QMessageBox.warning(self, "Error", "Property name cannot be empty.")
                return
            # Prevent using known structural tags as property names
            if prop_name in self.KNOWN_ITEM_CHILD_TAGS or prop_name in self.KNOWN_ABILITY_CHILD_TAGS:
                 QMessageBox.warning(self, "Error", f"'{prop_name}' is a reserved structural tag name and cannot be used as a property.")
                 return
            if self.current_selection_element.find(prop_name) is not None:
                 QMessageBox.warning(self, "Error", f"A property named '{prop_name}' already exists for this ability.")
                 return

            # --- Add element and update UI ---
            logging.info(f"Adding property '{prop_name}' to ability '{self.current_selection_name}'")
            new_element = ET.SubElement(self.current_selection_element, prop_name)
            # Add some sensible default attributes
            new_element.set('type', 'add')
            new_element.set('min', '0')
            new_element.set('max', '0') # Add max as well?
            self.mark_file_modified(self.current_selection_filepath)

            # Update completer model for property *names* if new
            if prop_name not in self.all_property_names:
                self.all_property_names.add(prop_name)
                self._update_single_completer_model(self.property_name_model, self.all_property_names, "property_name")

            # Update completer model for property *attribute names* if defaults are new
            added_attrs = {'type', 'min', 'max'}
            new_global_attrs = added_attrs - self.all_property_attribute_names
            if new_global_attrs:
                 self.all_property_attribute_names.update(new_global_attrs)
                 self._update_single_completer_model(self.property_attribute_name_model, self.all_property_attribute_names, "property_attribute_name")

            # Add the UI widget for the new property
            prop_widget = PropertyWidget(new_element, self.current_selection_filepath, self)
            self.properties_layout.addWidget(prop_widget)
            if not self.properties_section.isVisible():
                 self.set_ability_specific_visibility(True)
            logging.debug(f"Added property UI widget for: {prop_name}")


    # --- Add/Remove/Duplicate Main Entries ---

    def add_entry(self):
        """Adds a new Ability or Item entry."""
        if self._populating_details: return

        if not self.loaded_files:
            QMessageBox.warning(self, "Action Failed", "No XML files are loaded. Please open a folder first.")
            return

        current_tab_index = self.tab_widget.currentIndex()
        entry_type = TAG_ABILITY if current_tab_index == 0 else TAG_ITEM
        entry_type_name = entry_type.capitalize() # For dialogs
        data_map = self.abilities_map if entry_type == TAG_ABILITY else self.items_map
        list_widget = self.ability_list if entry_type == TAG_ABILITY else self.item_list

        new_name, ok = QInputDialog.getText(self, f"Add New {entry_type_name}", f"Enter the unique name for the new {entry_type}:")

        if ok and new_name:
            new_name = new_name.strip()
            if not new_name:
                QMessageBox.warning(self, "Error", "The name cannot be empty.")
                return
            if new_name in data_map:
                QMessageBox.warning(self, "Error", f"An {entry_type} named '{new_name}' already exists.")
                return

            # --- Determine Target File and Parent Node ---
            target_filepath, parent_node = self._find_or_create_target_node(entry_type)

            if parent_node is None or target_filepath is None:
                 QMessageBox.critical(self, "Critical Error", f"Could not find or create a suitable parent node (<{TAG_ABILITIES if entry_type == TAG_ABILITY else TAG_ITEMS}>) in any loaded XML file.")
                 return

            # --- Create New Element with Defaults ---
            logging.info(f"Adding new {entry_type} '{new_name}' to file '{os.path.basename(target_filepath)}'...")
            new_element = self._create_default_element(entry_type, new_name, parent_node)

            # --- Update Data Structures and UI ---
            data_map[new_name] = {'filepath': target_filepath, 'element': new_element}
            self.mark_file_modified(target_filepath)

            # Add to list and select
            list_item = QListWidgetItem(new_name)
            list_widget.addItem(list_item)
            list_widget.sortItems()
            list_widget.setCurrentItem(list_item) # Selection triggers populate_details

            # Update relevant name completer model
            if entry_type == TAG_ABILITY:
                self.all_ability_names.add(new_name)
                self._update_single_completer_model(self.ability_name_model, self.all_ability_names, "ability_name")
            else:
                self.all_item_names.add(new_name)
                self._update_single_completer_model(self.item_name_model, self.all_item_names, "item_name")

            logging.info(f"Successfully added new {entry_type}: {new_name}")
            self.statusBar.showMessage(f"Added: {new_name}", 3000)

        elif ok and not new_name.strip(): # Handled case where OK is pressed with empty input
             QMessageBox.warning(self, "Error", "The name cannot be empty.")
        # else: User cancelled dialog


    def _find_or_create_target_node(self, entry_type):
        """Finds the best file/parent node (<abilities> or <items>) to add a new entry to, creating if necessary."""
        parent_node_tag = TAG_ABILITIES if entry_type == TAG_ABILITY else TAG_ITEMS
        target_filepath = None
        parent_node = None
        root_to_modify = None

        # Priority 1: Use the currently selected file if available
        if self.current_selection_filepath and self.current_selection_filepath in self.loaded_files:
            target_filepath = self.current_selection_filepath
            root_to_modify = self.loaded_files[target_filepath]['root']
            logging.debug(f"Add Entry: Targeting currently selected file: {target_filepath}")
            # Look for parent node directly under <definitions> or root
            definitions_node = root_to_modify.find('definitions')
            if definitions_node is not None:
                parent_node = definitions_node.find(parent_node_tag)
            if parent_node is None: # Check directly under root if not in definitions
                 parent_node = root_to_modify.find(parent_node_tag)

            # If parent still not found in *this* file, create it
            if parent_node is None:
                logging.warning(f"Node <{parent_node_tag}> not found in '{target_filepath}'. Creating structure...")
                # Ensure <definitions> exists (common practice)
                if definitions_node is None:
                    definitions_node = ET.SubElement(root_to_modify, 'definitions')
                    logging.debug("  Created <definitions> node.")
                parent_node = ET.SubElement(definitions_node, parent_node_tag)
                logging.debug(f"  Created <{parent_node_tag}> node inside <definitions>.")
            return target_filepath, parent_node

        # Priority 2: Find the *first* loaded file containing the parent node
        logging.debug("Add Entry: No current selection. Searching loaded files for target node...")
        for fp, data in self.loaded_files.items():
            root = data['root']
            # Use findall to search anywhere (more flexible)
            found_nodes = root.findall(f".//{parent_node_tag}")
            if found_nodes:
                target_filepath = fp
                parent_node = found_nodes[0] # Use the first one found
                root_to_modify = root
                logging.debug(f"  Found existing <{parent_node_tag}> node in file: {fp}")
                return target_filepath, parent_node

        # Priority 3: Create node in the *first* loaded file if not found anywhere
        logging.warning(f"Add Entry: Node <{parent_node_tag}> not found in any loaded file. Creating in first file.")
        if not self.loaded_files:
            logging.error("Add Entry: Cannot create node, no files loaded.")
            return None, None # Should be caught earlier, but safety check

        target_filepath = next(iter(self.loaded_files)) # Get path of first loaded file
        root_to_modify = self.loaded_files[target_filepath]['root']
        definitions_node = root_to_modify.find('definitions')
        if definitions_node is None:
            definitions_node = ET.SubElement(root_to_modify, 'definitions')
            logging.debug(f"  Created <definitions> node in {target_filepath}.")
        # Check again inside definitions just in case
        parent_node = definitions_node.find(parent_node_tag)
        if parent_node is None:
            parent_node = ET.SubElement(definitions_node, parent_node_tag)
            logging.debug(f"  Created <{parent_node_tag}> node inside <definitions> in {target_filepath}.")
        return target_filepath, parent_node

    def _create_default_element(self, entry_type, name, parent_node):
        """Creates a new ability/item element with default children."""
        new_element = ET.SubElement(parent_node, entry_type)
        new_element.set('name', name)
        ET.SubElement(new_element, TAG_TAGS) # Add empty tags element

        if entry_type == TAG_ITEM:
            # Add default attributes and empty structure sections for items
            new_element.set('category', 'misc') # Example defaults
            new_element.set('price', '1')
            ET.SubElement(new_element, TAG_BASE_ABILITIES)
            ET.SubElement(new_element, TAG_RECYCLING_PARTS)
            ET.SubElement(new_element, TAG_VARIANTS)
        elif entry_type == TAG_ABILITY:
            # Add defaults for ability if needed
            # ET.SubElement(new_element, ...)
            pass

        logging.debug(f"Created default structure for new {entry_type} '{name}'")
        return new_element

    def remove_entry(self):
        """Removes the currently selected Ability or Item."""
        if self._populating_details: return
        if not self.current_selection_element:
            QMessageBox.warning(self, "Action Failed", "Please select an item or ability to remove.")
            return

        entry_type = self.current_selection_type
        name = self.current_selection_name
        element = self.current_selection_element
        file_path = self.current_selection_filepath
        entry_type_name = entry_type.capitalize()
        data_map = self.abilities_map if entry_type == TAG_ABILITY else self.items_map
        list_widget = self.ability_list if entry_type == TAG_ABILITY else self.item_list

        confirm = QMessageBox.question(self, f"Remove {entry_type_name}",
                                     f"Are you sure you want to permanently remove the {entry_type} '{name}'?\n\n(This action affects the XML file '{os.path.basename(file_path)}'.)",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)

        if confirm == QMessageBox.StandardButton.Yes:
            logging.info(f"Attempting to remove {entry_type} '{name}' from {file_path}")
            parent_element = self.get_parent_element(element, file_path)

            if parent_element is not None:
                try:
                    parent_element.remove(element)
                    self.mark_file_modified(file_path)
                    logging.info(f"Removed element <{entry_type}> '{name}' from XML.")

                    # Remove from internal tracking
                    if name in data_map:
                        del data_map[name]
                        logging.debug(f"Removed '{name}' from internal {entry_type} map.")

                    # Remove from UI list
                    items = list_widget.findItems(name, Qt.MatchFlag.MatchExactly)
                    if items:
                        row = list_widget.row(items[0])
                        list_widget.takeItem(row)
                        logging.debug(f"Removed '{name}' from UI list.")
                    else:
                        logging.warning(f"Could not find item '{name}' in UI list to remove.")

                    self.clear_details_pane() # Clear the right pane
                    self.statusBar.showMessage(f"Removed: {name}", 3000)
                    logging.info(f"Successfully removed {entry_type}: {name}")

                    # Update name completer model
                    if entry_type == TAG_ABILITY:
                        if name in self.all_ability_names: self.all_ability_names.remove(name)
                        self._update_single_completer_model(self.ability_name_model, self.all_ability_names, "ability_name")
                    else:
                        if name in self.all_item_names: self.all_item_names.remove(name)
                        self._update_single_completer_model(self.item_name_model, self.all_item_names, "item_name")


                except ValueError:
                    logging.error(f"Element '{name}' not found in parent <{parent_element.tag}> during remove attempt (ValueError).", exc_info=True)
                    QMessageBox.critical(self, "Internal Error", f"Could not find the element '{name}' in the XML structure to remove it.")
                except Exception as e:
                    logging.error(f"Error removing {entry_type} '{name}': {e}", exc_info=True)
                    QMessageBox.critical(self, "Removal Error", f"An error occurred while removing '{name}':\n{e}")
            else:
                # This indicates get_parent_element failed
                logging.error(f"Could not find parent element for {entry_type} '{name}' in file '{file_path}'. Removal aborted.")
                QMessageBox.critical(self, "Internal Error", f"Could not locate the parent container for '{name}' in the file.")


    def duplicate_entry(self):
        """Duplicates the currently selected Ability or Item."""
        if self._populating_details: return
        if not self.current_selection_element:
            QMessageBox.warning(self, "Action Failed", "Please select an item or ability to duplicate.")
            return

        original_name = self.current_selection_name
        original_element = self.current_selection_element
        original_filepath = self.current_selection_filepath
        entry_type = self.current_selection_type
        entry_type_name = entry_type.capitalize()
        data_map = self.abilities_map if entry_type == TAG_ABILITY else self.items_map
        list_widget = self.ability_list if entry_type == TAG_ABILITY else self.item_list

        new_name_suggestion = f"{original_name}_copy"
        # Ensure suggestion is unique
        count = 1
        while new_name_suggestion in data_map:
            count += 1
            new_name_suggestion = f"{original_name}_copy{count}"

        new_name, ok = QInputDialog.getText(self, f"Duplicate {entry_type_name}",
                                          f"Enter the unique name for the copy of '{original_name}':",
                                          text=new_name_suggestion)

        if ok and new_name:
            new_name = new_name.strip()
            if not new_name:
                QMessageBox.warning(self, "Error", "The name cannot be empty.")
                return
            if new_name == original_name:
                 QMessageBox.warning(self, "Error", "The duplicate name must be different from the original.")
                 return
            if new_name in data_map:
                QMessageBox.warning(self, "Error", f"An {entry_type} named '{new_name}' already exists.")
                return

            logging.info(f"Attempting to duplicate {entry_type} '{original_name}' as '{new_name}' in file '{os.path.basename(original_filepath)}'")
            parent_element = self.get_parent_element(original_element, original_filepath)

            if parent_element is not None:
                try:
                    # --- Create Deep Copy and Insert ---
                    new_element = copy.deepcopy(original_element)
                    new_element.set('name', new_name) # Set the new name

                    # Insert the new element immediately after the original one if possible
                    try:
                        parent_list = list(parent_element) # Get children as a list
                        original_index = parent_list.index(original_element)
                        parent_element.insert(original_index + 1, new_element)
                        logging.debug(f"Inserted duplicate after original at index {original_index + 1}.")
                    except (ValueError, IndexError):
                        # Fallback if original not found or index issue
                        logging.warning("Could not find original element index. Appending duplicate to the end.")
                        parent_element.append(new_element)
                    # --- End Insertion ---

                    # Update data map and mark file modified
                    data_map[new_name] = {'filepath': original_filepath, 'element': new_element}
                    self.mark_file_modified(original_filepath)
                    logging.info(f"Duplicated '{original_name}' as '{new_name}' in XML.")

                    # Add to UI list and select
                    list_item = QListWidgetItem(new_name)
                    list_widget.addItem(list_item)
                    list_widget.sortItems()
                    list_widget.setCurrentItem(list_item) # Selection triggers populate_details

                    # Update name completer model
                    if entry_type == TAG_ABILITY:
                        self.all_ability_names.add(new_name)
                        self._update_single_completer_model(self.ability_name_model, self.all_ability_names, "ability_name")
                    else:
                        self.all_item_names.add(new_name)
                        self._update_single_completer_model(self.item_name_model, self.all_item_names, "item_name")

                    self.statusBar.showMessage(f"Duplicated as: {new_name}", 3000)
                    logging.info(f"Successfully duplicated '{original_name}' as '{new_name}'.")

                except Exception as e:
                    logging.error(f"Error duplicating {entry_type} '{original_name}': {e}", exc_info=True)
                    QMessageBox.critical(self, "Duplication Error", f"An error occurred while duplicating '{original_name}':\n{e}")
                    # Clean up potentially inconsistent state? Difficult.
                    if new_name in data_map: del data_map[new_name] # Remove from map if added

            else:
                # Parent not found - should not happen if selection is valid
                logging.error(f"Could not find parent element for {entry_type} '{original_name}' during duplication.")
                QMessageBox.critical(self, "Internal Error", f"Could not locate the parent container for '{original_name}' to perform duplication.")

        elif ok and not new_name.strip():
             QMessageBox.warning(self, "Error", "The name cannot be empty.")
        # else: User cancelled dialog

    # --- Helpers ---

    def get_parent_element(self, child_element, file_path):
        """Finds the direct parent of a given lxml element within its file's tree."""
        if file_path not in self.loaded_files:
            logging.error(f"get_parent_element: File path '{file_path}' not in loaded files.")
            return None
        root = self.loaded_files[file_path]['root']

        # lxml's getparent() is usually efficient and reliable
        parent = child_element.getparent()
        if parent is not None:
             # Basic check: is the found parent actually part of the expected root?
             # This helps catch detached elements, although shouldn't happen with current structure.
             if parent is root or any(p is parent for p in root.iter()):
                 # logging.debug(f"Found parent <{parent.tag}> for <{child_element.tag}> using getparent()")
                 return parent
             else:
                 logging.warning(f"Found parent <{parent.tag}> via getparent(), but it seems detached from the root of {file_path}.")
                 # Fallback to iteration? Or trust getparent()? Trusting getparent() is usually okay.
                 return parent # Return it anyway for now

        # Fallback iteration (less efficient, but backup)
        logging.debug(f"getparent() failed for <{child_element.tag}>. Falling back to iteration...")
        for p_elem in root.iter():
            # Check if p_elem is iterable and child_element is in its direct children
            try:
                # Convert children to list for reliable 'in' check
                if child_element in list(p_elem):
                    logging.debug(f"Found parent <{p_elem.tag}> for <{child_element.tag}> via iteration.")
                    return p_elem
            except TypeError:
                pass # p_elem is not iterable (e.g., comment, PI)

        logging.warning(f"Could not find parent for element <{child_element.tag}> (Name: {child_element.get('name', 'N/A')}) in file '{os.path.basename(file_path)}'.")
        return None

    def _check_unsaved_changes(self, action_description="continue"):
        """Checks for modified files and prompts the user to save, discard, or cancel."""
        if not self.modified_files:
            return QMessageBox.StandardButton.Yes # No changes, proceed

        file_count = len(self.modified_files)
        file_s = "file" if file_count == 1 else "files"
        message = f"You have unsaved changes in {file_count} {file_s}.\n\nDo you want to save them before you {action_description}?"

        reply = QMessageBox.warning(self, 'Unsaved Changes', message,
                                    QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel) # Default to Cancel

        if reply == QMessageBox.StandardButton.Save:
            logging.info("User chose to Save changes before proceeding.")
            self.save_all_files()
            # Check if saving failed (files still modified)
            if self.modified_files:
                logging.warning("Save failed for some files. Action cancelled.")
                QMessageBox.warning(self, "Save Failed", "Could not save all files. The action has been cancelled.")
                return QMessageBox.StandardButton.Cancel # Treat as cancel if save fails
            else:
                return QMessageBox.StandardButton.Save # Save succeeded
        elif reply == QMessageBox.StandardButton.Discard:
            logging.info("User chose to Discard changes.")
            # Clear the modified flag for all files *without* saving
            self.modified_files.clear()
            self.update_window_title() # Update title bar
            return QMessageBox.StandardButton.Discard
        else: # Cancel
            logging.info(f"Action '{action_description}' cancelled by user due to unsaved changes.")
            return QMessageBox.StandardButton.Cancel

    # Override closeEvent
    def closeEvent(self, event):
        """Handles the window close event, checking for unsaved changes."""
        logging.info("Close event triggered.")
        result = self._check_unsaved_changes("exit the application")

        if result == QMessageBox.StandardButton.Cancel:
            logging.info("Window close cancelled.")
            event.ignore() # Prevent window from closing
        else:
            logging.info("Window close accepted.")
            # Save config before exiting? Yes.
            self.save_config()
            event.accept() # Allow window to close


    # --- List Filtering ---
    def filter_list(self, text, list_widget):
        """Filters the items in a QListWidget based on the input text."""
        filter_text = text.lower()
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item: # Check if item is valid
                item_text = item.text().lower()
                # Simple contains check
                item.setHidden(filter_text not in item_text)

    def filter_abilities(self, text):
        self.filter_list(text, self.ability_list)

    def filter_items(self, text):
        self.filter_list(text, self.item_list)


# --- Main Application Execution ---
if __name__ == "__main__":
    # Enable DPI scaling for sharper UI on high-res displays
    if hasattr(Qt.ApplicationAttribute, 'AA_EnableHighDpiScaling'):
         QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
         logging.debug("High DPI Scaling enabled.")
    if hasattr(Qt.ApplicationAttribute, 'AA_UseHighDpiPixmaps'):
         QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
         logging.debug("High DPI Pixmaps enabled.")

    app = QApplication(sys.argv)

    # Apply basic Fusion dark palette (same as before)
    app.setStyle("Fusion")
    dark_palette = QPalette()
    # ... (palette colors remain the same as in your original code) ...
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.black)
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
    app.setPalette(dark_palette)
    logging.debug("Dark Fusion palette applied.")

    # Create and show the main window
    editor = WitcherXMLEditor()
    editor.show()

    # Start the application event loop
    sys.exit(app.exec())