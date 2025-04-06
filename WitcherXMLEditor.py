import sys
import os
from lxml import etree as ET # Używamy lxml.etree jako ET
import copy
import configparser # <-- NOWY IMPORT
from pathlib import Path # <-- NOWY IMPORT
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QSplitter, QTabWidget, QListWidget, QListWidgetItem, QLineEdit,
    QPushButton, QLabel, QScrollArea, QSizePolicy, QSpacerItem, QGridLayout,
    QFileDialog, QMessageBox, QInputDialog, QCompleter, QMenuBar, QStatusBar, QDialog,
)
from PySide6.QtCore import QMargins, Qt, QStringListModel, Signal
from PySide6.QtGui import QAction, QPalette, QColor, QShortcut, QKeySequence, QIcon

# --- Custom Widget for Generic Properties (like in Abilities) ---
class PropertyWidget(QWidget):
    def __init__(self, element, file_path, editor_instance, parent=None):
        super().__init__(parent)
        self.element = element
        self.file_path = file_path
        self.editor = editor_instance

        # --- GŁÓWNY LAYOUT POZIOMY DLA CAŁEGO WIERSZA ---
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0) # Usuń zewnętrzne marginesy

        # --- 1. Etykieta Nazwy Właściwości ---
        self.name_label = QLabel(f"{element.tag}:")
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.name_label.setFixedWidth(150) # Ustaw stałą szerokość dla wyrównania
        self.main_layout.addWidget(self.name_label)

        # --- 2. Kontener i Layout dla Atrybutów ---
        # Użyjemy QWidget jako kontenera, aby łatwiej zarządzać layoutem atrybutów
        self.attributes_container = QWidget()
        self.attributes_layout = QHBoxLayout(self.attributes_container) # Layout *tylko* dla atrybutów
        self.attributes_layout.setContentsMargins(5, 0, 5, 0) # Mały margines wewnętrzny
        self.attributes_layout.setAlignment(Qt.AlignLeft) # Trzymaj atrybuty blisko siebie po lewej
        self.main_layout.addWidget(self.attributes_container) # Dodaj kontener do głównego layoutu

        self.attribute_widgets = {} # Słownik do przechowywania widgetów QLineEdit

        # Dodaj widgety dla istniejących atrybutów do layoutu atrybutów
        for key, value in sorted(element.attrib.items()):
            attr_label = QLabel(f"{key}:")
            attr_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            attr_input = QLineEdit(value)
            attr_input.setObjectName(f"prop_input_{element.tag}_{key}") # Unikalna nazwa obiektu

            # Dołącz QCompleter
            if key == 'type':
                 self.editor._attach_completer(attr_input, self.editor.property_attr_type_model)
            elif key == 'always_random': # Zakładając, że to pole tekstowe dla true/false
                 self.editor._attach_completer(attr_input, self.editor.boolean_value_model)
            # Dodaj inne elif dla specyficznych atrybutów, jeśli potrzeba

            attr_input.editingFinished.connect(lambda k=key, i=attr_input: self.attribute_changed(k, i.text()))

            self.attributes_layout.addWidget(attr_label) # Dodaj do layoutu *atrybutów*
            self.attributes_layout.addWidget(attr_input) # Dodaj do layoutu *atrybutów*
            self.attribute_widgets[key] = attr_input

        # --- 3. Rozciągliwy Spacer PRZED przyciskami ---
        self.main_layout.addStretch(1)

        # --- 4. Przycisk "+Attr" ---
        self.add_attr_button = QPushButton("+Attr") # Zapisz referencję jako atrybut instancji
        self.add_attr_button.setFixedWidth(50)
        self.add_attr_button.setToolTip("Dodaj nowy atrybut do tej właściwości")
        self.add_attr_button.clicked.connect(self.add_attribute)
        self.main_layout.addWidget(self.add_attr_button) # Dodaj do głównego layoutu

        # --- 5. Przycisk "X" (Usuń Właściwość) ---
        self.remove_button = QPushButton("X") # Zapisz referencję jako atrybut instancji
        self.remove_button.setFixedWidth(30)
        self.remove_button.setToolTip(f"Usuń całą właściwość '{element.tag}'")
        self.remove_button.clicked.connect(self.remove_self)
        self.main_layout.addWidget(self.remove_button) # Dodaj do głównego layoutu
        
       

    def attribute_changed(self, key, new_value):
        # Bez zmian - ta funkcja jest OK
        if self.editor._populating_details: return
        old_value = self.element.get(key)
        if old_value != new_value:
            print(f"Property Attr '{key}' changed from '{old_value}' to '{new_value}' for <{self.element.tag}>")
            self.element.set(key, new_value)
            self.editor.mark_file_modified(self.file_path)

    def add_attribute(self):
        """Dodaje nowy atrybut do tej konkretnej właściwości (elementu)."""
        if self.editor._populating_details: return

        # Dialog do wpisania nazwy nowego atrybutu
        dialog = QInputDialog(self.editor) # Użyj głównego okna jako rodzica
        dialog.setWindowTitle("Add Property Attribute")
        dialog.setLabelText("Name of new attribute:")
        line_edit = dialog.findChild(QLineEdit)
        if line_edit:
            # Dołącz model z nazwami znanych atrybutów właściwości
            self.editor._attach_completer(line_edit, self.editor.property_attribute_name_model)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            attr_name = dialog.textValue().strip().replace(" ", "_") # Podstawowe oczyszczenie
            if attr_name and attr_name not in self.element.attrib:
                # Dodaj atrybut do elementu XML
                default_value = "" # Można ustawić domyślną wartość, np. "0" lub "false"
                self.element.set(attr_name, default_value)
                self.editor.mark_file_modified(self.file_path)

                # --- Dynamicznie dodaj widgety do UI ---
                attr_label = QLabel(f"{attr_name}:")
                attr_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
                attr_input = QLineEdit(default_value)
                attr_input.setObjectName(f"prop_input_{self.element.tag}_{attr_name}") # Unikalna nazwa obiektu

                # Dołącz odpowiedni completer, jeśli nazwa atrybutu jest znana (np. 'type')
                if attr_name == 'type':
                    self.editor._attach_completer(attr_input, self.editor.property_attr_type_model)
                elif attr_name == 'always_random':
                    self.editor._attach_completer(attr_input, self.editor.boolean_value_model)
                # Dodaj inne warunki, jeśli trzeba

                attr_input.editingFinished.connect(lambda k=attr_name, i=attr_input: self.attribute_changed(k, i.text()))

                # Dodaj nowe widgety do layoutu atrybutów (self.attributes_layout)
                self.attributes_layout.addWidget(attr_label)
                self.attributes_layout.addWidget(attr_input)
                self.attribute_widgets[attr_name] = attr_input # Śledź nowy widget
                print(f"Dodano atrybut '{attr_name}' do <{self.element.tag}>")

                # Zaktualizuj zbiór nazw atrybutów właściwości i model
                if attr_name not in self.editor.all_property_attribute_names:
                    self.editor.all_property_attribute_names.add(attr_name)
                    # Ponowne sortowanie i ustawienie modelu (może być kosztowne przy wielu dodaniach)
                    self.editor.property_attribute_name_model.setStringList(sorted(list(self.editor.all_property_attribute_names)))

            elif attr_name in self.element.attrib:
                QMessageBox.warning(self, "Error", f"Atrybut '{attr_name}' już istnieje dla tej właściwości.")
            elif not attr_name:
                 QMessageBox.warning(self, "Error", "Nazwa atrybutu nie może być pusta.")

    def remove_self(self):
        """Usuwa całą tę właściwość (PropertyWidget) i odpowiadający jej element XML."""
        if self.editor._populating_details: return
        confirm = QMessageBox.question(self, "Usuń Właściwość", f"Czy na pewno chcesz usunąć całą właściwość '{self.element.tag}'?")
        if confirm == QMessageBox.StandardButton.Yes:
            parent_element = self.editor.get_parent_element(self.element, self.file_path)
            if parent_element is not None:
                try:
                    parent_element.remove(self.element)
                    self.editor.mark_file_modified(self.file_path)
                    # Usunięcie widgetu spowoduje automatyczne usunięcie go z layoutu
                    self.deleteLater()
                    print(f"Removed property widget and element: {self.element.tag}")
                    # Uwaga: Nie odświeżamy całego panelu, aby uniknąć ponownego tworzenia wszystkiego
                    # Można by ewentualnie wyemitować sygnał, jeśli inne części UI muszą zareagować.
                except ValueError:
                    print(f"Error: Element {self.element.tag} not found in parent during remove_self.")
                    self.deleteLater() # Usuń widget mimo błędu XML
                except Exception as e:
                    print(f"Error removing property widget/element: {e}")
                    self.deleteLater()
            else:
                print(f"Error: Could not find parent element for {self.element.tag} to remove.")
                self.deleteLater() # Usuń widget, nawet jeśli nie można usunąć elementu XML

class WitcherXMLEditor(QMainWindow):
   
   
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Witcher 3 XML Editor v1.0") # Zmieniono tytuł
         
        base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        icon_path = base_path / "editor_icon.ico"  # <-- upewnij się, że .ico!

        print(f"Szukam ikony pod: {icon_path}")
        print("Plik istnieje?", icon_path.exists())

        if icon_path.exists():
            icon = QIcon(str(icon_path))
            self.setWindowIcon(icon)
            QApplication.setWindowIcon(icon)
            print("Ikona ustawiona.")
        else:
            print("Nie znaleziono pliku ikony.")
        
        
        self.setGeometry(100, 100, 1200, 800)

        # --- Ścieżka do pliku konfiguracyjnego ---
        if getattr(sys, 'frozen', False):
            self.base_path = Path(sys.executable).parent
        else:
            self.base_path = Path(__file__).parent
        self.config_file = self.base_path / "editor_config.ini"
        self.last_folder = ""
        
        

        # --- Przechowywanie Danych ---
        self.loaded_files = {}
        self.abilities_map = {}
        self.items_map = {}
        self.modified_files = set()

        # --- Zbiory Danych do Autouzupełniania ---
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
        self.all_anim_actions = set() # Zbiorczy dla draw/holster act/deact

        # --- Referencje do Akcji Menu ---
        self.open_action = None
        self.save_action = None
        self.save_all_action = None
        self.save_as_action = None
        self.exit_action = None
        self.author_action = None # <<< DODAJ REFERENCJĘ

        # --- Zbiory Pomocnicze / Stałe ---
        self.known_item_child_tags = {'tags', 'base_abilities', 'recycling_parts', 'variants'}

        # --- Zmienne Stanu Aplikacji ---
        self.current_selection_name = None
        self.current_selection_type = None
        self.current_selection_element = None
        self.current_selection_filepath = None
        self._populating_details = False

        # --- Modele do Autouzupełniania ---
        self.item_attribute_name_model = QStringListModel(self) # Ustaw rodzica
        self.variant_attribute_name_model = QStringListModel(self)
        self.property_attribute_name_model = QStringListModel(self)
        self.ability_name_model = QStringListModel(self)
        self.item_name_model = QStringListModel(self)
        self.recycling_part_name_model = QStringListModel(self)
        self.item_category_model = QStringListModel(self)
        self.ability_mode_model = QStringListModel(self)
        self.variant_nested_tag_model = QStringListModel(self)
        self.tag_model = QStringListModel(self)
        self.property_name_model = QStringListModel(self)
        self.equip_template_model = QStringListModel(self)
        self.localisation_key_model = QStringListModel(self)
        self.icon_path_model = QStringListModel(self)
        self.property_attr_type_model = QStringListModel(self)
        self.equip_slot_model = QStringListModel(self)
        self.boolean_value_model = QStringListModel(["true", "false"], self) # Statyczny
        self.hold_slot_model = QStringListModel(self)
        self.hand_model = QStringListModel(self)
        self.sound_id_model = QStringListModel(self)
        self.event_model = QStringListModel(self)
        self.anim_action_model = QStringListModel(self) # Model zbiorczy
        self.enhancement_slots_model = QStringListModel(["0", "1", "2", "3"], self) # Statyczny

        # --- Inicjalizacja UI i Sygnałów ---
        self._init_ui()
        self._connect_signals()

        # --- Pasek Stanu ---
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready.")
        self.author_label = QLabel("Gerwant 2025")
        self.statusBar.addPermanentWidget(self.author_label) # Dodaj jako stały widget

        # --- Wczytaj konfigurację i spróbuj załadować ostatni folder ---
        self.load_config()
        if self.last_folder and Path(self.last_folder).is_dir():
            print(f"The last used folder in the configuration was found: {self.last_folder}")
            self.load_folder_on_startup(self.last_folder)
        else:
            print("No saved folder or folder does not exist. Use 'File -> Open folder...'..")
            self.statusBar.showMessage("Ready. Open the folder with the XML files.")
   
      
    def _init_ui(self):
        # --- Menu Bar ---
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        # Twórz akcje i PRZYPISUJ je do atrybutów self.*
        self.open_action = QAction("Open folder with XML files...", self)
        file_menu.addAction(self.open_action)

        self.save_action = QAction("Save", self)
        file_menu.addAction(self.save_action)

        self.save_all_action = QAction("Save all", self) # Zmieniona kolejność, aby pasowała do __init__
        file_menu.addAction(self.save_all_action)

        self.save_as_action = QAction("Save as...", self) # Stworzenie i przypisanie
        file_menu.addAction(self.save_as_action) # Dodanie do menu

        file_menu.addSeparator()
        
        help_menu = menu_bar.addMenu("Help") # Używamy "Pomoc" dla spójności językowej
        self.author_action = QAction("Autor", self) # Stwórz i zapisz referencję
        help_menu.addAction(self.author_action)

      #  self.exit_action = QAction("Exit", self)
      #  file_menu.addAction(self.exit_action)
        # --- Koniec Menu Bar ---


        # --- Main Splitter ---
        splitter = QSplitter(Qt.Horizontal); self.setCentralWidget(splitter)

        # --- Left Pane ---
        left_widget = QWidget(); left_layout = QVBoxLayout(left_widget)
        self.tab_widget = QTabWidget(); left_layout.addWidget(self.tab_widget)
        # Abilities Tab
        self.ability_tab = QWidget(); ability_layout = QVBoxLayout(self.ability_tab)
        self.ability_filter = QLineEdit(); self.ability_filter.setPlaceholderText("Filter by name...")
        self.ability_list = QListWidget()
        ability_layout.addWidget(self.ability_filter); ability_layout.addWidget(self.ability_list)
        self.tab_widget.addTab(self.ability_tab, "Abilities")
        # Items Tab
        self.item_tab = QWidget(); item_layout = QVBoxLayout(self.item_tab)
        self.item_filter = QLineEdit(); self.item_filter.setPlaceholderText("Filter by name...")
        self.item_list = QListWidget()
        item_layout.addWidget(self.item_filter); item_layout.addWidget(self.item_list)
        self.tab_widget.addTab(self.item_tab, "Items")
        # Action Buttons
        button_layout = QHBoxLayout()
        self.add_button = QPushButton("Add"); self.remove_button = QPushButton("Delete"); self.duplicate_button = QPushButton("Duplicate")
        button_layout.addWidget(self.add_button); button_layout.addWidget(self.remove_button); button_layout.addWidget(self.duplicate_button)
        left_layout.addLayout(button_layout)
        splitter.addWidget(left_widget)
        # --- Koniec Left Pane ---

        # --- Right Pane ---
        right_scroll_area = QScrollArea(); right_scroll_area.setWidgetResizable(True)
        self.right_widget = QWidget(); self.right_layout = QVBoxLayout(self.right_widget)
        self.right_layout.setAlignment(Qt.AlignTop); right_scroll_area.setWidget(self.right_widget)

        # Common Fields
        name_layout = QHBoxLayout(); name_layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit(); self.name_input.setReadOnly(True)
        name_layout.addWidget(self.name_input); self.right_layout.addLayout(name_layout)

        tags_layout = QHBoxLayout(); tags_layout.addWidget(QLabel("Tags:"))
        self.tags_input = QLineEdit()
        # Dołącz completer od razu, bo model tags_model istnieje od __init__
        self._attach_completer(self.tags_input, self.tag_model)
        tags_layout.addWidget(self.tags_input); self.right_layout.addLayout(tags_layout)

        # Item Specific Sections & Buttons
        self.item_attributes_header = self.create_section_header("Item Attributes")
        self.item_attributes_section = QWidget(); self.item_attributes_layout = QGridLayout(self.item_attributes_section)
        self.item_attributes_layout.setObjectName("ItemAttributesLayout"); self.item_attributes_layout.setAlignment(Qt.AlignTop)
        self.right_layout.addWidget(self.item_attributes_header); self.right_layout.addWidget(self.item_attributes_section)

        self.base_abilities_header = self.create_section_header("Base Abilities")
        self.base_abilities_section = QWidget(); self.base_abilities_layout = QVBoxLayout(self.base_abilities_section)
        self.base_abilities_layout.setObjectName("BaseAbilitiesLayout"); self.base_abilities_layout.setAlignment(Qt.AlignTop)
        self.right_layout.addWidget(self.base_abilities_header); self.right_layout.addWidget(self.base_abilities_section)
        self.add_base_ability_button = QPushButton("Add a Base Abilities"); self.right_layout.addWidget(self.add_base_ability_button, alignment=Qt.AlignLeft)

        self.recycling_parts_header = self.create_section_header("Recycling Parts")
        self.recycling_parts_section = QWidget(); self.recycling_parts_layout = QVBoxLayout(self.recycling_parts_section)
        self.recycling_parts_layout.setObjectName("RecyclingPartsLayout"); self.recycling_parts_layout.setAlignment(Qt.AlignTop)
        self.right_layout.addWidget(self.recycling_parts_header); self.right_layout.addWidget(self.recycling_parts_section)
        self.add_recycling_part_button = QPushButton("Add Part"); self.right_layout.addWidget(self.add_recycling_part_button, alignment=Qt.AlignLeft)

        self.variants_header = self.create_section_header("Variants")
        self.variants_section = QWidget(); self.variants_layout = QVBoxLayout(self.variants_section)
        self.variants_layout.setObjectName("VariantsLayout"); self.variants_layout.setAlignment(Qt.AlignTop)
        self.right_layout.addWidget(self.variants_header); self.right_layout.addWidget(self.variants_section)
        self.add_variant_button = QPushButton("Add Variant"); self.right_layout.addWidget(self.add_variant_button, alignment=Qt.AlignLeft)

        # Generic Properties Section (for Abilities)
        self.properties_header = self.create_section_header("Properties")
        self.properties_section = QWidget(); self.properties_layout = QVBoxLayout(self.properties_section)
        self.properties_layout.setObjectName("PropertiesLayout"); self.properties_layout.setContentsMargins(10, 5, 0, 5)
        self.properties_layout.setAlignment(Qt.AlignTop)
        self.right_layout.addWidget(self.properties_header); self.right_layout.addWidget(self.properties_section)
        self.add_property_button = QPushButton("Add Property"); self.right_layout.addWidget(self.add_property_button, alignment=Qt.AlignLeft)

        # Initial visibility setup
        self.set_item_specific_visibility(False)
        self.set_ability_specific_visibility(False)

        self.right_layout.addStretch(1); splitter.addWidget(right_scroll_area)
        splitter.setSizes([300, 900])
        # --- Koniec Right Pane ---

    
    def show_author_info(self):
        """Wyświetla okno informacyjne o autorze."""
        author_text = """Created by Gerwant. Thank you for using my program.

        Feel free to visit my NexusMods page:
        https://next.nexusmods.com/profile/gerwant30

        and my YouTube channel:
        https://www.youtube.com/@TalesoftheWitcher

        Cheers!"""
        # Użyj QMessageBox dla prostego okna informacyjnego
        msg_box = QMessageBox(self) # Ustaw główne okno jako rodzica
        msg_box.setWindowTitle("O Autorze")
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setTextFormat(Qt.TextFormat.PlainText) # Ustaw format na zwykły tekst
        msg_box.setText(author_text)
        # Opcjonalnie, aby linki były klikalne (wymaga RichText)
        # msg_box.setTextFormat(Qt.TextFormat.RichText)
        # msg_box.setText(author_text.replace("\n", "<br/>").replace("https://", "<a href='https://")) # Prosta konwersja na HTML
        msg_box.exec() # Użyj exec() dla modala
    
    
    def load_config(self):
        """Wczytuje konfigurację z pliku ini."""
        config = configparser.ConfigParser()
        try:
            if self.config_file.exists():
                config.read(self.config_file, encoding='utf-08')
                if 'Settings' in config and 'LastFolder' in config['Settings']:
                    folder = config['Settings']['LastFolder']
                    # Prosta walidacja - czy to wygląda jak ścieżka (nie jest puste)
                    if folder:
                        self.last_folder = folder
                        print(f"Wczytano ostatni folder z konfiguracji: {self.last_folder}")
                    else:
                        print("Wpis 'LastFolder' w konfiguracji jest pusty.")
                else:
                    print("Brak sekcji [Settings] lub wpisu 'LastFolder' w pliku konfiguracyjnym.")
            else:
                print(f"Plik konfiguracyjny {self.config_file} nie istnieje. Zostanie utworzony przy zapisie.")
        except configparser.Error as e:
            print(f"Błąd odczytu pliku konfiguracyjnego: {e}")
        except Exception as e:
             print(f"Nieoczekiwany błąd podczas wczytywania konfiguracji: {e}")


    def save_config(self):
        """Zapisuje aktualną konfigurację (ostatni folder) do pliku ini."""
        config = configparser.ConfigParser()
        try:
            # Odczytaj istniejący plik, aby nie nadpisać innych ustawień (jeśli będą w przyszłości)
            if self.config_file.exists():
                config.read(self.config_file, encoding='utf-08')

            # Upewnij się, że sekcja [Settings] istnieje
            if 'Settings' not in config:
                config['Settings'] = {}

            # Zapisz ostatnio używany folder
            config['Settings']['LastFolder'] = self.last_folder if self.last_folder else "" # Zapisz pusty, jeśli nie ma

            # Zapisz do pliku
            with open(self.config_file, 'w', encoding='utf-08') as configfile:
                config.write(configfile)
            print(f"Konfiguracja zapisana w: {self.config_file} (LastFolder: {self.last_folder})")

        except IOError as e:
             print(f"Błąd zapisu pliku konfiguracyjnego: {e}")
             QMessageBox.warning(self, "Błąd konfiguracji", f"Nie można zapisać pliku konfiguracyjnego:\n{e}")
        except Exception as e:
             print(f"Nieoczekiwany błąd podczas zapisywania konfiguracji: {e}")


    def load_folder_on_startup(self, folder_path):
        """Próbuje załadować pliki z podanego folderu przy starcie."""
        self.statusBar.showMessage(f"Automatic loading of files from: {folder_path}...")
        QApplication.processEvents() # Zaktualizuj UI
        try:
            self.load_xml_files(folder_path)
            self.populate_lists()
            self.statusBar.showMessage(f"Loaded files from: {folder_path}. Select an element.", 5000)
        except Exception as e:
             error_msg = f"An error occurred during the automatic loading of files from the {folder_path}:\n{e}"
             print(error_msg)
             QMessageBox.critical(self, "Automatic loading error", error_msg)
             self.statusBar.showMessage("Error during automatic file loading.", 5000)
             self.last_folder = "" # Wyzeruj, jeśli ładowanie się nie powiodło

    def create_section_header(self, text):
        # ... (same as before) ...
        header = QLabel(text)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout = QVBoxLayout()
        layout.addWidget(header)
        layout.addWidget(line)
        container = QWidget()
        container.setLayout(layout)
        return container

    def set_item_specific_visibility(self, visible):
        """Shows/hides all item-specific sections and buttons."""
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
        self.properties_header.setVisible(visible)
        self.properties_section.setVisible(visible)
        self.add_property_button.setVisible(visible)

    def _connect_signals(self):
        # --- Połączenia dla list, filtrów i przycisków pod listami ---
        self.ability_list.currentItemChanged.connect(lambda current, _: self.list_item_selected(current, 'ability'))
        self.item_list.currentItemChanged.connect(lambda current, _: self.list_item_selected(current, 'item'))
        self.ability_filter.textChanged.connect(self.filter_abilities)
        self.item_filter.textChanged.connect(self.filter_items)
        self.add_button.clicked.connect(self.add_entry)
        self.remove_button.clicked.connect(self.remove_entry)
        self.duplicate_button.clicked.connect(self.duplicate_entry)
        # --- Koniec połączeń dla lewego panelu ---

        # --- Połączenia dla Akcji z Paska Menu ---
        # Używamy referencji przechowywanych w self.*_action
        if self.open_action:
            self.open_action.triggered.connect(self.open_folder)
        else:
            print("OSTRZEŻENIE: self.open_action nie zostało zainicjalizowane.")

        if self.save_action:
            self.save_action.triggered.connect(self.save_current_file)
        else:
            print("OSTRZEŻENIE: self.save_action nie zostało zainicjalizowane.")

        if self.save_all_action:
            self.save_all_action.triggered.connect(self.save_all_files)
        else:
            print("OSTRZEŻENIE: self.save_all_action nie zostało zainicjalizowane.")

        if self.save_as_action: # Sprawdź, czy akcja "Zapisz jako..." istnieje
            self.save_as_action.triggered.connect(self.save_as_current_file)
        else:
            # Ten log jest mniej prawdopodobny, jeśli _init_ui działa poprawnie, ale zostawmy dla pewności
            print("OSTRZEŻENIE: self.save_as_action nie zostało zainicjalizowane.")

        if self.exit_action:
            self.exit_action.triggered.connect(self.close) # Użyj self.close zamiast QApplication.quit dla obsługi zapisu
        else:
            print("OSTRZEŻENIE: self.exit_action nie zostało zainicjalizowane.")
            
        if self.author_action:
            self.author_action.triggered.connect(self.show_author_info)
        else:
            print("OSTRZEŻENIE: self.author_action nie zostało zainicjalizowane.")
        # --- Koniec połączeń dla Paska Menu ---


        # --- Połączenia dla edycji w Prawym Panelu ---
        self.tags_input.editingFinished.connect(self.tags_changed)
        self.add_property_button.clicked.connect(self.add_property) # Dla Abilities
        self.add_base_ability_button.clicked.connect(self.add_base_ability) # Dla Items
        self.add_recycling_part_button.clicked.connect(self.add_recycling_part) # Dla Items
        self.add_variant_button.clicked.connect(self.add_variant) # Dla Items
        # --- Koniec połączeń dla Prawego Panelu ---


    # --- File Operations ---

    def open_folder(self):
        """Otwiera dialog wyboru folderu i ładuje pliki XML."""
        print("Wywołano Otwórz folder...") # Dodajmy log dla pewności

        # 1. Sprawdź niezapisane zmiany (jeśli istnieją)
        if self.modified_files:
            reply = QMessageBox.question(self, 'Niezapisane Zmiany',
                                         "Masz niezapisane zmiany. Czy chcesz je zapisać przed otwarciem nowego folderu?",
                                         QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                         QMessageBox.StandardButton.Cancel) # Domyślnie Anuluj

            if reply == QMessageBox.StandardButton.Save:
                self.save_all_files()
                # Sprawdź ponownie, czy zapis się powiódł
                if self.modified_files:
                    QMessageBox.warning(self, "Błąd Zapisu", "Niektóre pliki nie mogły zostać zapisane. Otwieranie folderu anulowane.")
                    return # Nie kontynuuj
            elif reply == QMessageBox.StandardButton.Cancel:
                print("Anulowano otwieranie folderu z powodu niezapisanych zmian.")
                return # Nie kontynuuj
            # Jeśli wybrano Discard, kontynuujemy poniżej

        # --- POCZĄTEK FRAGMENTU DO WSTAWIENIA ---
        # 2. Ustalanie folderu startowego dla dialogu QFileDialog
        start_dir = self.base_path # Domyślnie folder, gdzie jest aplikacja/skrypt
        if self.last_folder and Path(self.last_folder).is_dir():
            # Jeśli mamy zapamiętany folder i on istnieje, użyj go
            start_dir = self.last_folder
            print(f"Dialog otworzy się w ostatnio używanym folderze: {start_dir}")
        else:
            # Jeśli nie ma zapamiętanego lub nie istnieje, użyj folderu aplikacji
            print(f"Brak zapamiętanego folderu lub nie istnieje. Dialog otworzy się w: {start_dir}")
        # Upewnij się, że start_dir jest stringiem dla QFileDialog
        start_dir_str = str(start_dir)
        # --- KONIEC FRAGMENTU DO WSTAWIENIA ---

        # 3. Otwórz dialog wyboru folderu, zaczynając od start_dir_str
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Wybierz folder z plikami XML gry",
            start_dir_str  # Użyj ustalonej ścieżki startowej
        )

        # 4. Przetwórz wybrany folder (lub anulowanie)
        if folder_path:
            # Użytkownik wybrał folder
            print(f"Wybrano folder: {folder_path}")
            selected_path = Path(folder_path) # Konwertuj na obiekt Path dla spójności

            # Sprawdź jeszcze raz, czy to na pewno folder (QFileDialog powinien to zapewnić)
            if selected_path.is_dir():
                 # --- Zapisz nowo wybrany folder jako ostatnio używany ---
                 new_last_folder = str(selected_path)
                 if self.last_folder != new_last_folder: # Zapisz tylko jeśli się zmienił
                     self.last_folder = new_last_folder
                     self.save_config() # Zapisz konfigurację
                 # --- Koniec zapisu ---

                 # --- Załaduj pliki z wybranego folderu ---
                 self.statusBar.showMessage(f"Loading files from: {folder_path}..."); QApplication.processEvents()
                 try:
                     self.load_xml_files(folder_path)
                     self.populate_lists()
                     self.statusBar.showMessage(f"Loaded files from: {folder_path}. Select an element.", 5000)
                 except Exception as e:
                      error_msg = f"An error occurred while loading files from {folder_path}:\n{e}"; print(error_msg)
                      QMessageBox.critical(self, "Loading error", error_msg)
                      self.statusBar.showMessage("Error when loading files.", 5000)
                      # Jeśli ładowanie zawiodło, nie traktuj tego folderu jako "działającego" ostatniego
                      if self.last_folder == new_last_folder:
                          self.last_folder = ""
                          self.save_config() # Zapisz pusty
                 # --- Koniec ładowania ---
            else:
                 # Teoretycznie nie powinno się zdarzyć z getExistingDirectory
                 print(f"OSTRZEŻENIE: QFileDialog zwrócił ścieżkę, która nie jest folderem: {folder_path}")
                 QMessageBox.warning(self, "Error", "The selected path is not a valid folder.")
        else:
             # Użytkownik anulował dialog
             print("Anulowano wybór folderu w dialogu.")
             self.statusBar.showMessage("The opening of the folder was cancelled.", 3000)
             



    def load_xml_files(self, folder_path):
        self.clear_data()
        count = 0; ability_count = 0; item_count = 0
        print(f"Rozpoczynanie ładowania plików XML z: {folder_path}")

        # Inicjalizacja zbiorów tymczasowych
        temp_prop_names = set(); temp_item_attr_names = set()
        temp_variant_attr_names = set(); temp_prop_attr_names = set()
        temp_tags = set(); temp_ability_names = set(); temp_item_names = set()
        temp_recycling_parts = set(); temp_item_categories = set()
        temp_ability_modes = set(); temp_variant_nested_tags = set()
        temp_equip_templates = set(); temp_loc_keys = set(); temp_icon_paths = set()
        temp_prop_attr_types = set(); temp_equip_slots = set()
        temp_hold_slots = set(); temp_hands = set(); temp_sound_ids = set(); temp_events = set()
        temp_anim_actions = set()

        for root_dir, _, files in os.walk(folder_path):
            for filename in files:
                if filename.lower().endswith(".xml"):
                    file_path = os.path.join(root_dir, filename)
                    try:
                        parser = ET.XMLParser(remove_comments=False)
                        tree = ET.parse(file_path, parser=parser)
                        root = tree.getroot()
                        if root is None: print(f"OSTRZEŻENIE: Pusty korzeń w pliku {file_path}"); continue
                        self.loaded_files[file_path] = {'tree': tree, 'root': root}; count += 1

                        # --- ABILITIES ---
                        for abilities_node in root.findall('.//abilities'):
                            for ability in abilities_node.findall('ability'):
                                name = ability.get('name')
                                if name and name not in self.abilities_map:
                                    self.abilities_map[name] = {'filepath': file_path, 'element': ability}; ability_count += 1
                                    temp_ability_names.add(name)
                                    for prop in ability:
                                        if ET.iselement(prop):
                                            if prop.tag == 'tags':
                                                 if prop.text: temp_tags.update(t.strip() for t in prop.text.split(',') if t.strip())
                                            else:
                                                 temp_prop_names.add(prop.tag)
                                                 temp_prop_attr_names.update(prop.attrib.keys())
                                                 prop_type = prop.get('type')
                                                 if prop_type: temp_prop_attr_types.add(prop_type)

                        # --- ITEMS ---
                        for items_node in root.findall('.//items'):
                             for item in items_node.findall('item'):
                                name = item.get('name')
                                if name and name not in self.items_map:
                                    self.items_map[name] = {'filepath': file_path, 'element': item}; item_count += 1
                                    temp_item_names.add(name)
                                    temp_item_attr_names.update(item.attrib.keys())

                                    # Zbierz wartości atrybutów item
                                    cat = item.get('category'); mode = item.get('ability_mode')
                                    eq_tmpl = item.get('equip_template'); eq_slot = item.get('equip_slot')
                                    hold_s = item.get('hold_slot'); hand_v = item.get('hand')
                                    sound = item.get('sound_identification')
                                    draw_e = item.get('draw_event'); holster_e = item.get('holster_event')
                                    draw_act_v = item.get('draw_act'); draw_deact_v = item.get('draw_deact')
                                    holster_act_v = item.get('holster_act'); holster_deact_v = item.get('holster_deact')
                                    loc_key_n = item.get('localisation_key_name'); loc_key_d = item.get('localisation_key_description')
                                    icon_p = item.get('icon_path')

                                    if cat: temp_item_categories.add(cat)
                                    if mode: temp_ability_modes.add(mode)
                                    if eq_tmpl: temp_equip_templates.add(eq_tmpl)
                                    if eq_slot: temp_equip_slots.add(eq_slot)
                                    if hold_s: temp_hold_slots.add(hold_s)
                                    if hand_v: temp_hands.add(hand_v)
                                    if sound: temp_sound_ids.add(sound)
                                    if draw_e: temp_events.add(draw_e)
                                    if holster_e: temp_events.add(holster_e)
                                    if draw_act_v: temp_anim_actions.add(draw_act_v)
                                    if draw_deact_v: temp_anim_actions.add(draw_deact_v)
                                    if holster_act_v: temp_anim_actions.add(holster_act_v)
                                    if holster_deact_v: temp_anim_actions.add(holster_deact_v)
                                    if loc_key_n: temp_loc_keys.add(loc_key_n)
                                    if loc_key_d: temp_loc_keys.add(loc_key_d)
                                    if icon_p: temp_icon_paths.add(icon_p)

                                    # Przetwórz dzieci item
                                    for child in item:
                                        if ET.iselement(child):
                                            tag = child.tag
                                            if tag == 'tags':
                                                 if child.text: temp_tags.update(t.strip() for t in child.text.split(',') if t.strip())
                                            elif tag == 'recycling_parts':
                                                 for part in child.findall('parts'):
                                                     if part.text: temp_recycling_parts.add(part.text.strip())
                                            elif tag == 'variants':
                                                 for variant in child.findall('variant'):
                                                     temp_variant_attr_names.update(variant.attrib.keys())
                                                     var_eq_tmpl = variant.get('equip_template')
                                                     if var_eq_tmpl: temp_equip_templates.add(var_eq_tmpl)
                                                     for nested in variant:
                                                         if ET.iselement(nested): temp_variant_nested_tags.add(nested.tag)
                                            elif tag not in self.known_item_child_tags:
                                                 temp_prop_names.add(tag)
                                                 temp_prop_attr_names.update(child.attrib.keys())

                    except ET.XMLSyntaxError as e: print(f"BŁĄD PARSOWANIA XML (lxml) w pliku {file_path}: {e}")
                    except Exception as e: print(f"BŁĄD podczas przetwarzania pliku {file_path}: {e}")

        # --- Aktualizacja atrybutów klasy ---
        self.all_property_names = temp_prop_names; self.all_item_attribute_names = temp_item_attr_names
        self.all_variant_attribute_names = temp_variant_attr_names; self.all_property_attribute_names = temp_prop_attr_names
        self.all_tags = temp_tags; self.all_ability_names = temp_ability_names; self.all_item_names = temp_item_names
        self.all_recycling_part_names = temp_recycling_parts; self.all_item_categories = temp_item_categories
        self.all_ability_modes = temp_ability_modes; self.all_variant_nested_tags = temp_variant_nested_tags
        self.all_equip_templates = temp_equip_templates; self.all_loc_keys = temp_loc_keys
        self.all_icon_paths = temp_icon_paths; self.all_prop_attr_types = temp_prop_attr_types
        self.all_equip_slots = temp_equip_slots; self.all_hold_slots = temp_hold_slots
        self.all_hands = temp_hands; self.all_sound_ids = temp_sound_ids; self.all_events = temp_events
        self.all_anim_actions = temp_anim_actions

        # --- Aktualizacja modeli QStringListModel (TYLKO RAZ, z funkcją safe_sorted_string_list) ---
        print("Aktualizowanie modeli do autouzupełniania...")

        # Funkcja pomocnicza do bezpiecznego sortowania i filtrowania tylko stringów
        def safe_sorted_string_list(data_set, set_name="nieznany"):
            string_list = []; invalid_items_details = []
            for item in data_set:
                if isinstance(item, str): string_list.append(item)
                else:
                    item_repr = repr(item); item_type = type(item).__name__
                    details = f"Typ: {item_type}, Repr: {item_repr}"; invalid_items_details.append(details)
            if invalid_items_details:
                 print(f"  OSTRZEŻENIE: Znaleziono i POMINIĘTO {len(invalid_items_details)} elementów niebędących str w '{set_name}':")
                 for detail in invalid_items_details: print(f"    - {detail}")
            try: return sorted(string_list)
            except TypeError as e_sort: print(f"  KRYTYCZNY BŁĄD SORTOWANIA (po filtrowaniu!) dla '{set_name}': {e_sort}. Lista: {string_list}"); return string_list

        # Wywołania setStringList z użyciem safe_sorted_string_list
        try: self.item_attribute_name_model.setStringList(safe_sorted_string_list(self.all_item_attribute_names, "all_item_attribute_names"))
        except Exception as e: print(f"BŁĄD aktualizacji item_attribute_name_model: {e}")
        try: self.variant_attribute_name_model.setStringList(safe_sorted_string_list(self.all_variant_attribute_names, "all_variant_attribute_names"))
        except Exception as e: print(f"BŁĄD aktualizacji variant_attribute_name_model: {e}")
        try: self.property_attribute_name_model.setStringList(safe_sorted_string_list(self.all_property_attribute_names, "all_property_attribute_names"))
        except Exception as e: print(f"BŁĄD aktualizacji property_attribute_name_model: {e}")
        try: self.ability_name_model.setStringList(safe_sorted_string_list(self.all_ability_names, "all_ability_names"))
        except Exception as e: print(f"BŁĄD aktualizacji ability_name_model: {e}")
        try: self.item_name_model.setStringList(safe_sorted_string_list(self.all_item_names, "all_item_names"))
        except Exception as e: print(f"BŁĄD aktualizacji item_name_model: {e}")
        try: self.recycling_part_name_model.setStringList(safe_sorted_string_list(self.all_recycling_part_names, "all_recycling_part_names"))
        except Exception as e: print(f"BŁĄD aktualizacji recycling_part_name_model: {e}")
        try: self.item_category_model.setStringList(safe_sorted_string_list(self.all_item_categories, "all_item_categories"))
        except Exception as e: print(f"BŁĄD aktualizacji item_category_model: {e}")
        try: self.ability_mode_model.setStringList(safe_sorted_string_list(self.all_ability_modes, "all_ability_modes"))
        except Exception as e: print(f"BŁĄD aktualizacji ability_mode_model: {e}")
        try: self.variant_nested_tag_model.setStringList(safe_sorted_string_list(self.all_variant_nested_tags, "all_variant_nested_tags"))
        except Exception as e: print(f"BŁĄD aktualizacji variant_nested_tag_model: {e}")
        try: self.tag_model.setStringList(safe_sorted_string_list(self.all_tags, "all_tags"))
        except Exception as e: print(f"BŁĄD aktualizacji tag_model: {e}")
        try: self.property_name_model.setStringList(safe_sorted_string_list(self.all_property_names, "all_property_names"))
        except Exception as e: print(f"BŁĄD aktualizacji property_name_model: {e}")
        try: self.equip_template_model.setStringList(safe_sorted_string_list(self.all_equip_templates, "all_equip_templates"))
        except Exception as e: print(f"BŁĄD aktualizacji equip_template_model: {e}")
        try: self.localisation_key_model.setStringList(safe_sorted_string_list(self.all_loc_keys, "all_loc_keys"))
        except Exception as e: print(f"BŁĄD aktualizacji localisation_key_model: {e}")
        try: self.icon_path_model.setStringList(safe_sorted_string_list(self.all_icon_paths, "all_icon_paths"))
        except Exception as e: print(f"BŁĄD aktualizacji icon_path_model: {e}")
        try: self.property_attr_type_model.setStringList(safe_sorted_string_list(self.all_prop_attr_types, "all_prop_attr_types"))
        except Exception as e: print(f"BŁĄD aktualizacji property_attr_type_model: {e}")
        try: self.equip_slot_model.setStringList(safe_sorted_string_list(self.all_equip_slots, "all_equip_slots"))
        except Exception as e: print(f"BŁĄD aktualizacji equip_slot_model: {e}")
        try: self.hold_slot_model.setStringList(safe_sorted_string_list(self.all_hold_slots, "all_hold_slots"))
        except Exception as e: print(f"BŁĄD aktualizacji hold_slot_model: {e}")
        try: self.hand_model.setStringList(safe_sorted_string_list(self.all_hands, "all_hands"))
        except Exception as e: print(f"BŁĄD aktualizacji hand_model: {e}")
        try: self.sound_id_model.setStringList(safe_sorted_string_list(self.all_sound_ids, "all_sound_ids"))
        except Exception as e: print(f"BŁĄD aktualizacji sound_id_model: {e}")
        try: self.event_model.setStringList(safe_sorted_string_list(self.all_events, "all_events"))
        except Exception as e: print(f"BŁĄD aktualizacji event_model: {e}")
        try: self.anim_action_model.setStringList(safe_sorted_string_list(self.all_anim_actions, "all_anim_actions"))
        except Exception as e: print(f"BŁĄD aktualizacji anim_action_model: {e}")

        print("Aktualizacja modeli zakończona.")

        # --- Podsumowanie ładowania ---
        print(f"Zakończono ładowanie. Załadowano {count} plików XML.")
        print(f"  Znaleziono {ability_count} unikalnych umiejętności ({len(self.all_ability_names)} w sumie).")
        print(f"  Znaleziono {item_count} unikalnych przedmiotów ({len(self.all_item_names)} w sumie).")
        print(f"  Zebrano {len(self.all_equip_slots)} unikalnych slotów ekwipunku.")
        print(f"  Zebrano {len(self.all_hold_slots)} unikalnych slotów trzymania.")
        print(f"  Zebrano {len(self.all_hands)} unikalnych wartości 'hand'.")
        print(f"  Zebrano {len(self.all_sound_ids)} unikalnych ID dźwięków.")
        print(f"  Zebrano {len(self.all_events)} unikalnych nazw eventów.")
        print(f"  Zebrano {len(self.all_anim_actions)} unikalnych nazw akcji animacji.")

    def save_file(self, file_path):
        # ... (same as before) ...
        if file_path in self.loaded_files and file_path in self.modified_files:
            tree = self.loaded_files[file_path]['tree']
            try:
                tree.write(file_path,
                           pretty_print=True,         # Włącz ładne formatowanie (wcięcia, nowe linie)
                           encoding='utf-16',         # Utrzymaj kodowanie
                           xml_declaration=True)      # Zachowaj deklarację <?xml...>
                # --- KONIEC ZMIANY ---
                self.modified_files.remove(file_path)
                self.statusBar.showMessage(f"Saved: {os.path.basename(file_path)}", 3000); print(f"Saved: {file_path}")
                return True
            except Exception as e: QMessageBox.critical(self, "Błąd Zapisu", f"Błąd zapisu {file_path}:\n{e}"); return False
        return False

    def save_current_file(self): # ... (same as before) ...
        if self.current_selection_filepath: self.save_file(self.current_selection_filepath); self.update_window_title()
        else: QMessageBox.information(self, "Save", "Element not selected.")

    def save_all_files(self): # ... (same as before) ...
        if not self.modified_files: QMessageBox.information(self, "Save all", "No change."); return
        reply = QMessageBox.question(self, "Save all", f"Save {len(self.modified_files)} changed files?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            saved_count = 0; failed_count = 0
            for file_path in list(self.modified_files):
                if self.save_file(file_path): saved_count += 1
                else: failed_count += 1
            msg = f"Saved {saved_count} files."; msg += f" Errors: {failed_count}." if failed_count > 0 else ""
            self.statusBar.showMessage(msg, 5000); self.update_window_title()
            
            
    def save_as_current_file(self):
        """Zapisuje zawartość aktualnie aktywnego pliku XML do nowej lokalizacji
           i przełącza kontekst edytora na nowy plik."""
        print("Wywołano Zapisz jako...")

        # 1. Sprawdź, czy jest aktywny plik
        if not self.current_selection_filepath or self.current_selection_filepath not in self.loaded_files:
            QMessageBox.information(self, "Zapisz jako...", "Najpierw wybierz element z listy, aby określić plik do zapisania.")
            return

        original_filepath = self.current_selection_filepath
        original_name = self.current_selection_name # Zapamiętaj nazwę elementu
        original_type = self.current_selection_type # Zapamiętaj typ elementu
        tree = self.loaded_files[original_filepath]['tree'] # Pobierz drzewo XML z pamięci

        # 2. Zaproponuj nową ścieżkę pliku
        suggested_name = os.path.basename(original_filepath)
        name_part, ext_part = os.path.splitext(suggested_name)
        suggested_name_copy = f"{name_part}_copy{ext_part}"
        start_dir = os.path.dirname(original_filepath)

        new_filepath, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Zapisz plik XML jako...",
            os.path.join(start_dir, suggested_name_copy),
            "XML Files (*.xml);;All Files (*)"
        )

        # 3. Sprawdź, czy użytkownik wybrał plik
        if not new_filepath:
            print("Anulowano Zapisz jako...")
            self.statusBar.showMessage("Anulowano zapisywanie jako.", 3000)
            return

        if not new_filepath.lower().endswith(".xml"):
            new_filepath += ".xml"

        # 4. Zapisz drzewo do nowej ścieżki
        print(f"Próba zapisu kopii do: {new_filepath}")
        try:
            tree.write(new_filepath,
                       pretty_print=True,
                       encoding='utf-16',
                       xml_declaration=True)
            print(f"Pomyślnie zapisano kopię jako: {new_filepath}")
            self.statusBar.showMessage(f"Zapisano jako: {os.path.basename(new_filepath)}", 4000)

            # 5. Aktualizacja stanu edytora, jeśli zapisano pod *inną* nazwą/ścieżką
            if new_filepath != original_filepath:
                print(f"Aktualizowanie stanu edytora na plik: {new_filepath}")

                # Dodaj nowy plik do załadowanych (używamy tego samego obiektu drzewa na razie)
                new_root = tree.getroot() # Pobierz korzeń z zapisanego drzewa
                self.loaded_files[new_filepath] = {'tree': tree, 'root': new_root}

                # Zaktualizuj mapy, aby elementy z tego drzewa wskazywały na nowy plik
                data_map = self.abilities_map if original_type == 'ability' else self.items_map
                parent_node_tag = 'abilities' if original_type == 'ability' else 'items'
                child_tag = original_type # 'ability' lub 'item'

                # Znajdź węzeł rodzica w nowym (zapisanym) drzewie
                parent_node = new_root.find(f".//{parent_node_tag}")
                if parent_node is not None:
                    updated_count = 0
                    for element in parent_node.findall(child_tag):
                        elem_name = element.get('name')
                        if elem_name and elem_name in data_map:
                            # Jeśli element z mapy pochodził z oryginalnego pliku,
                            # lub jeśli po prostu chcemy przypisać go do nowego pliku
                            # (bezpieczniejsze podejście - zakładamy, że cały zapisany plik teraz "należy" do nowej ścieżki)
                            if data_map[elem_name]['filepath'] == original_filepath:
                                data_map[elem_name]['filepath'] = new_filepath
                                # Opcjonalnie zaktualizuj referencję elementu, choć lxml może to obsługiwać
                                data_map[elem_name]['element'] = element
                                updated_count += 1
                            elif data_map[elem_name]['filepath'] == new_filepath:
                                 # Jeśli już wskazuje na nowy plik (np. po poprzednim save as), upewnij się, że element jest aktualny
                                 data_map[elem_name]['element'] = element

                        elif elem_name: # Jeśli elementu nie było w mapie (np. dodany przed save as)
                             data_map[elem_name] = {'filepath': new_filepath, 'element': element}
                             updated_count += 1
                    print(f"Zaktualizowano ścieżki dla {updated_count} elementów w mapie '{original_type}'.")


                # Usuń nowy plik ze zbioru zmodyfikowanych (bo właśnie go zapisaliśmy)
                if new_filepath in self.modified_files:
                    self.modified_files.remove(new_filepath)
                    print(f"Usunięto {new_filepath} ze zbioru zmodyfikowanych.")

                # Odśwież listy UI (aby odzwierciedlić potencjalne zmiany w mapach)
                self.populate_lists()

                # Spróbuj ponownie zaznaczyć zapisany element
                list_widget = self.ability_list if original_type == 'ability' else self.item_list
                items = list_widget.findItems(original_name, Qt.MatchExactly)
                if items:
                    print(f"Ponowne zaznaczanie elementu: {original_name}")
                    list_widget.setCurrentItem(items[0])
                    # Wywołanie setCurrentItem powinno wywołać list_item_selected -> populate_details,
                    # które teraz użyje nowej ścieżki z mapy i zaktualizuje tytuł okna.
                else:
                    print(f"OSTRZEŻENIE: Nie można ponownie zaznaczyć elementu '{original_name}' po Zapisz jako.")
                    self.clear_details_pane() # Wyczyść panel, jeśli nie można zaznaczyć

            else:
                # Jeśli użytkownik zapisał pod tą samą nazwą (nadpisał oryginał)
                print(f"Nadpisano oryginalny plik: {original_filepath}")
                # Usuń go ze zbioru zmodyfikowanych, bo został zapisany
                if original_filepath in self.modified_files:
                    self.modified_files.remove(original_filepath)
                self.update_window_title() # Zaktualizuj tytuł (usunie gwiazdkę)


        except Exception as e:
            error_msg = f"Nie udało się zapisać pliku jako '{new_filepath}':\n{e}"
            print(f"BŁĄD: {error_msg}")
            QMessageBox.critical(self, "Błąd Zapisu jako...", error_msg)
            self.statusBar.showMessage("Błąd podczas zapisywania jako.", 4000)        
            
    def mark_file_modified(self, file_path): # ... (same as before) ...
        if file_path not in self.modified_files: self.modified_files.add(file_path); print(f"Modified: {file_path}"); self.update_window_title()

    def update_window_title(self): # ... (same as before) ...
        title = "Witcher 3 XML Editor - v.1"; asterisk = ""
        if self.current_selection_filepath: title += f" - {os.path.basename(self.current_selection_filepath)}"
        if self.current_selection_filepath in self.modified_files: title += " (*)"
        elif self.modified_files: asterisk = " (+)" # Indicate other modified files
        self.setWindowTitle(title + asterisk)

    # --- UI Population and Updates ---
    def clear_layout(self, layout):
        # ... (Updated version with debug prints from previous response) ...
        if layout is not None:
            # print(f"Clearing layout: {layout.objectName() if layout.objectName() else layout}") # DEBUG Optional
            while layout.count() > 0:
                item = layout.takeAt(0)
                if item is None: continue
                widget = item.widget()
                if widget is not None: widget.deleteLater()
                else:
                    sub_layout = item.layout()
                    if sub_layout is not None: self.clear_layout(sub_layout)
            # print(f"Layout cleared: {layout}") # DEBUG Optional
        # else: print("Attempted to clear a None layout") # DEBUG Optional

    def clear_details_pane(self):
         """Czyści prawy panel szczegółów i resetuje stan wyszukiwania."""
         self._populating_details = True # Zapobiegaj sygnałom podczas czyszczenia
         try:
             # --- Czyszczenie pól i layoutów ---
             self.name_input.clear()
             self.tags_input.clear()
             self.clear_layout(self.item_attributes_layout)
             self.clear_layout(self.base_abilities_layout)
             self.clear_layout(self.recycling_parts_layout)
             self.clear_layout(self.variants_layout)
             self.clear_layout(self.properties_layout) # Generic properties

             # --- Ukrywanie sekcji specyficznych dla typu ---
             self.set_item_specific_visibility(False)
             self.set_ability_specific_visibility(False)

             # --- Resetowanie Stanu Wyszukiwania ---
             if hasattr(self, 'search_bar_widget') and self.search_bar_widget.isVisible():
                 # Jeśli pasek wyszukiwania istnieje i jest widoczny, ukryj go
                 # Ukrycie paska przez toggle_search_bar wywoła też clear_search_highlights
                 self.toggle_search_bar()
             elif hasattr(self, '_search_widgets'): # Jeśli pasek był ukryty, ale mogły być podświetlenia
                 self.clear_search_highlights() # Tylko wyczyść podświetlenia i stan
             # --- Koniec Resetowania Wyszukiwania ---

             # --- Resetowanie stanu zaznaczenia ---
             self.current_selection_name = None
             self.current_selection_type = None
             self.current_selection_element = None
             self.current_selection_filepath = None

             # Zaktualizuj tytuł okna
             self.update_window_title()

         finally:
             self._populating_details = False # Zezwól na sygnały ponownie

 

    # --- Helper to create and attach completer ---

    def _attach_completer(self, line_edit, model):
        """Tworzy QCompleter i dołącza go do QLineEdit. Wersja 4."""
        field_name_label_text = f"Nieznane Pole ({line_edit.objectName()})" # Domyślna z objectName
        parent_widget = line_edit.parentWidget()
        parent_layout = parent_widget.layout() if parent_widget else None

        # print(f"\n  --- DEBUG _attach_completer ---")
        # print(f"  line_edit: {line_edit} (ObjectName: {line_edit.objectName()})")
        # print(f"  parent_widget: {parent_widget}")
        # print(f"  parent_layout: {parent_layout} (Typ: {type(parent_layout).__name__})")

        if parent_layout:
            item_index = parent_layout.indexOf(line_edit)
            # print(f"  item_index w layoucie: {item_index}")

            # --- Logika dla QGridLayout ---
            if isinstance(parent_layout, QGridLayout) and item_index != -1:
                # print(f"    Layout to QGridLayout.")
                try:
                    row, col, _, _ = parent_layout.getItemPosition(item_index)
                    if col > 0:
                        item_before = parent_layout.itemAtPosition(row, col - 1)
                        if item_before:
                             widget_before = item_before.widget()
                             if isinstance(widget_before, QLabel):
                                  field_name_label_text = widget_before.text().strip(': ')
                                  # print(f"        -> Grid: Ustawiono nazwę pola na: '{field_name_label_text}'")
                         # else: print(f"      Grid: Brak widgetu w pozycji ({row}, {col - 1})")
                    # else: print(f"    Grid: QLineEdit jest w pierwszej kolumnie (col={col}).")
                except Exception as e: print(f"    BŁĄD getItemPosition dla QGridLayout: {e}")

            # --- Logika dla QHBoxLayout (i innych liniowych) ---
            elif isinstance(parent_layout, QHBoxLayout) and item_index > 0:
                 # W QHBoxLayout często mamy Label, Input, Label, Input...
                 # Szukamy QLabel bezpośrednio przed QLineEdit
                 # print(f"    Layout to QHBoxLayout. Szukam itemu przed index {item_index}.")
                 widget_item_before = parent_layout.itemAt(item_index - 1)
                 if widget_item_before:
                     widget_before = widget_item_before.widget()
                     # print(f"      Znaleziono widget przed: {widget_before} (Typ: {type(widget_before).__name__})")
                     if isinstance(widget_before, QLabel):
                         field_name_label_text = widget_before.text().strip(': ')
                         # print(f"        -> HBox: Ustawiono nazwę pola na: '{field_name_label_text}'")
                 # else: print(f"      HBox: Brak widgetu przed QLineEdit (index={item_index - 1}).")
            # else: print(f"    Inny layout lub QLineEdit jest pierwszy.")
        # else: print(f"  BŁĄD: Nie znaleziono parent_layout dla {line_edit}")

        print(f"  -> Próba dołączenia kompletera do pola '{field_name_label_text}'...")
        if model is None: print(f"     BŁĄD: Model jest None."); return
        if model.rowCount() == 0: print(f"     INFO: Model jest pusty."); return

        print(f"     Model dla '{field_name_label_text}' zawiera {model.rowCount()} el.")
        completer = QCompleter(model, line_edit)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        line_edit.setCompleter(completer)
        print(f"      sukces! Kompleter dołączony do pola '{field_name_label_text}'.")
        # print(f"  --- KONIEC DEBUG _attach_completer ---")
    
    
    def clear_data(self):
        """Czyści wszystkie załadowane dane XML, mapy, zbiory i modele autouzupełniania."""
        print("Rozpoczynanie czyszczenia danych...")
        # 1. Wyczyść główne struktury danych
        self.loaded_files.clear()
        self.abilities_map.clear()
        self.items_map.clear()
        self.modified_files.clear()

        # 2. Wyczyść wszystkie zbiory ('set')
        self.all_property_names.clear()
        self.all_item_attribute_names.clear()
        self.all_variant_attribute_names.clear()
        self.all_property_attribute_names.clear()
        self.all_tags.clear()
        self.all_ability_names.clear()
        self.all_item_names.clear()
        self.all_recycling_part_names.clear()
        self.all_item_categories.clear()
        self.all_ability_modes.clear()
        self.all_variant_nested_tags.clear()
        self.all_equip_templates.clear()
        self.all_loc_keys.clear()
        self.all_icon_paths.clear()
        self.all_prop_attr_types.clear()
        self.all_equip_slots.clear()
        self.all_hold_slots.clear()   # <-- Dodany
        self.all_hands.clear()        # <-- Dodany
        self.all_sound_ids.clear()    # <-- Dodany
        self.all_events.clear()       # <-- Dodany
        self.all_anim_actions.clear() # <-- Dodany
        print("  Zbiory danych wyczyszczone.")

        # 3. Wyczyść modele QStringListModel
        self.item_attribute_name_model.setStringList([])
        self.variant_attribute_name_model.setStringList([])
        self.property_attribute_name_model.setStringList([])
        self.ability_name_model.setStringList([])
        self.item_name_model.setStringList([])
        self.recycling_part_name_model.setStringList([])
        self.item_category_model.setStringList([])
        self.ability_mode_model.setStringList([])
        self.variant_nested_tag_model.setStringList([])
        self.tag_model.setStringList([])
        self.property_name_model.setStringList([])
        self.equip_template_model.setStringList([])
        self.localisation_key_model.setStringList([])
        self.icon_path_model.setStringList([])
        self.property_attr_type_model.setStringList([])
        self.equip_slot_model.setStringList([])
        self.hold_slot_model.setStringList([])    # <-- Dodany
        self.hand_model.setStringList([])         # <-- Dodany
        self.sound_id_model.setStringList([])     # <-- Dodany
        self.event_model.setStringList([])        # <-- Dodany
        self.anim_action_model.setStringList([])  # <-- Dodany
        # Nie trzeba czyścić boolean_value_model i enhancement_slots_model (są statyczne)
        print("  Modele autouzupełniania wyczyszczone.")

        # 4. Wyczyść listy UI
        self.ability_list.clear()
        self.item_list.clear()
        print("  Listy UI wyczyszczone.")

        # 5. Wyczyść panel szczegółów
        self.clear_details_pane()
        print("  Panel szczegółów wyczyszczony.")

        # 6. Zaktualizuj tytuł okna
        self.update_window_title()

        print("Czyszczenie danych zakończone.")
          
    def populate_lists(self): # ... (same as before) ...
        print("Populating UI lists..."); self.ability_list.clear(); self.item_list.clear()
        ability_names = sorted(self.abilities_map.keys()); item_names = sorted(self.items_map.keys())
        for name in ability_names: self.ability_list.addItem(QListWidgetItem(name))
        for name in item_names: self.item_list.addItem(QListWidgetItem(name))
        print(f"Populated lists: {len(ability_names)} abilities, {len(item_names)} items.")

    def list_item_selected(self, current_item, item_type):
        if not current_item: self.clear_details_pane(); return
        name = current_item.text()
        if name == self.current_selection_name and item_type == self.current_selection_type: return # Avoid reload if same item
        print(f"\nSelected {item_type}: {name}") # DEBUG
        self.populate_details(name, item_type)

    def populate_details(self, name, item_type):
        self.clear_details_pane() # Clear first
        self._populating_details = True # Prevent signals during population
        try:
            data_map = self.abilities_map if item_type == 'ability' else self.items_map
            if name not in data_map: print(f"Error: '{name}' not found."); return

            item_data = data_map[name]
            element = item_data['element']
            file_path = item_data['filepath']

            self.current_selection_name = name; self.current_selection_type = item_type
            self.current_selection_element = element; self.current_selection_filepath = file_path

            # Populate Common Fields
            self.name_input.setText(name)
            tags_element = element.find('tags')
            self.tags_input.setText(tags_element.text.strip() if tags_element is not None and tags_element.text else "")

            # Populate Specific Sections
            if item_type == 'item':
                self.populate_item_details(element, file_path)
                self.set_item_specific_visibility(True)
                self.set_ability_specific_visibility(False)
            else: # 'ability'
                self.populate_ability_details(element, file_path)
                self.set_item_specific_visibility(False)
                self.set_ability_specific_visibility(True)

            self.update_window_title()
        finally:
             self._populating_details = False


    # --- Widget Add/Remove Helpers for Item Sections ---


    def add_base_ability_widget(self, ab_element):
        ability_text = ab_element.text.strip() if ab_element.text else ""
        print(f"    -> [add_base_ability_widget] Tworzenie widgetu dla: '{ability_text}'")

        widget = QWidget(); layout = QHBoxLayout(widget); layout.setContentsMargins(0,0,0,0)
        ab_input = QLineEdit(ability_text); ab_input.setPlaceholderText("Nazwa umiejętności")
        ab_input.setObjectName(f"input_base_ability_{id(ab_element)}")
        remove_button = QPushButton("X"); remove_button.setFixedWidth(30)

        # NAJPIERW DODAJ WIDGETY DO LAYOUTU
        layout.addWidget(ab_input)
        layout.addWidget(remove_button)
        self.base_abilities_layout.addWidget(widget) # Dodaj główny widget do layoutu sekcji

        # --- DOPIERO TERAZ DOŁĄCZ QCOMPLETER ---
        print(f"      -> [add_base_ability_widget] Próba dołączenia completera Ability Names...")
        self._attach_completer(ab_input, self.ability_name_model)
        # --- Koniec Dołączania ---

        # Połącz sygnały
        try: ab_input.editingFinished.disconnect()
        except RuntimeError: pass
        ab_input.editingFinished.connect(lambda elem=ab_element, inp=ab_input: self.base_ability_text_changed(elem, inp.text()))
        try: remove_button.clicked.disconnect()
        except RuntimeError: pass
        remove_button.clicked.connect(lambda w=widget, elem=ab_element: self.remove_list_widget(w, elem, 'base_abilities', self.base_abilities_layout))

        print(f"    <- [add_base_ability_widget] Widget dodany.")
        
            # --- DODAJ TĘ CAŁĄ FUNKCJĘ DO KLASY WitcherXMLEditor ---
    # Umieść ją np. po add_variant_widget lub razem z innymi funkcjami add_*_widget

    def add_nested_variant_item_widget(self, child_element, variant_element, layout):
        """Dodaje widget dla zagnieżdżonego elementu wewnątrz <variant> (np. <item>).
           Wersja z dodatkowym, bezpośrednim sprawdzaniem typu taga."""

        # --- Bezpieczne pobranie nazwy taga ---
        child_tag = None
        if ET.iselement(child_element): # Upewnij się, że to element
            tag_value = getattr(child_element, 'tag', None) # Bezpieczne pobranie atrybutu tag
            if isinstance(tag_value, str): # Sprawdź, czy pobrany tag jest stringiem
                child_tag = tag_value
        # --- Koniec bezpiecznego pobierania ---

        # Jeśli nie udało się uzyskać poprawnego stringa taga, loguj i zakończ
        if child_tag is None:
            print(f"  BŁĄD [add_nested...]: Nie można uzyskać poprawnego stringa taga dla elementu: {repr(child_element)}. Pomijanie.")
            return

        # Reszta funkcji używa teraz zmiennej child_tag, która *na pewno* jest stringiem
        child_text = child_element.text.strip() if child_element.text else ""
        print(f"          -> [add_nested_variant_item_widget] Tworzenie widgetu: Tag='{child_tag}', Text='{child_text}', layout docelowy: {layout}")

        nested_widget = QWidget()
        nested_layout = QHBoxLayout(nested_widget)
        nested_layout.setContentsMargins(0, 0, 0, 0)

        tag_label = QLabel(f"{child_tag}:"); tag_label.setFixedWidth(40)
        tag_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        nested_layout.addWidget(tag_label)

        text_input = QLineEdit(child_text)
        text_input.setObjectName(f"input_nested_{child_tag}_{id(child_element)}")

        # --- Dołącz completer na podstawie tagu ---
        print(f"            -> [add_nested...] Próba dołączenia kompletera dla taga '{child_tag}'...")
        # Teraz child_tag JEST stringiem, więc .lower() zadziała
        tag_lower = child_tag.lower()
        if tag_lower == 'item':
            self._attach_completer(text_input, self.item_name_model)
        elif tag_lower == 'ability':
             self._attach_completer(text_input, self.ability_name_model)
        else:
             print(f"            -> Brak zdefiniowanego kompletera dla taga '{child_tag}'.")
        # --- Koniec Dołączania ---
        nested_layout.addWidget(text_input)

        remove_nested_button = QPushButton("x"); remove_nested_button.setFixedWidth(25)
        remove_nested_button.setToolTip(f"Usuń ten element <{child_tag}>")
        nested_layout.addWidget(remove_nested_button)

        layout.addWidget(nested_widget) # Dodaj do layoutu przekazanego jako argument

        # --- Połącz sygnały ---
        try: text_input.editingFinished.disconnect()
        except RuntimeError: pass
        text_input.editingFinished.connect(lambda elem=child_element, inp=text_input: self.nested_variant_item_text_changed(elem, inp.text()))

        try: remove_nested_button.clicked.disconnect()
        except RuntimeError: pass
        remove_nested_button.clicked.connect(lambda w=nested_widget, elem=child_element, p_elem=variant_element: self.remove_nested_variant_item(w, elem, p_elem))

        print(f"          <- [add_nested_variant_item_widget] Widget dla <{child_tag}> dodany.")  
        

    def add_recycling_part_widget(self, part_element):
        count_value = part_element.get('count', '1'); part_text = part_element.text.strip() if part_element.text else ""
        print(f"    -> [add_recycling_part_widget] Tworzenie widgetu: Count='{count_value}', Name='{part_text}'")

        widget = QWidget(); layout = QHBoxLayout(widget); layout.setContentsMargins(0,0,0,0)
        label_ilosc = QLabel("Quantity:"); label_ilosc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        count_input = QLineEdit(count_value); count_input.setFixedWidth(50); count_input.setPlaceholderText("Quantity")
        count_input.setObjectName(f"input_recycling_count_{id(part_element)}")
        label_nazwa = QLabel(" Name:"); label_nazwa.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        name_input = QLineEdit(part_text); name_input.setPlaceholderText("Name of part")
        name_input.setObjectName(f"input_recycling_name_{id(part_element)}")
        remove_button = QPushButton("X"); remove_button.setFixedWidth(30)

        # NAJPIERW DODAJ WIDGETY DO LAYOUTU
        layout.addWidget(label_ilosc); layout.addWidget(count_input)
        layout.addWidget(label_nazwa); layout.addWidget(name_input); layout.addWidget(remove_button)
        self.recycling_parts_layout.addWidget(widget) # Dodaj główny widget do layoutu sekcji

        # --- DOPIERO TERAZ DOŁĄCZ QCOMPLETER DO POLA NAZWY ---
        print(f"      -> [add_recycling_part_widget] Próba dołączenia completera Part Names do pola NAZWY...")
        self._attach_completer(name_input, self.recycling_part_name_model)
        # --- Koniec Dołączania ---

        # Połącz sygnały
        try: count_input.editingFinished.disconnect()
        except RuntimeError: pass
        count_input.editingFinished.connect(lambda elem=part_element, inp=count_input: self.part_attribute_changed(elem, 'count', inp.text()))
        try: name_input.editingFinished.disconnect()
        except RuntimeError: pass
        name_input.editingFinished.connect(lambda elem=part_element, inp=name_input: self.part_text_changed(elem, inp.text()))
        try: remove_button.clicked.disconnect()
        except RuntimeError: pass
        remove_button.clicked.connect(lambda w=widget, elem=part_element: self.remove_list_widget(w, elem, 'recycling_parts', self.recycling_parts_layout))

        print(f"    <- [add_recycling_part_widget] Widget dodany.")

    def add_variant_widget(self, var_element):
        """Dodaje wiersz widgetu dla elementu <variant> element, obsługując atrybuty i zagnieżdżone dzieci."""
        # print(f"      -> add_variant_widget called for variant with attrs: {var_element.attrib}") # DEBUG
        variant_row_widget = QWidget()
        row_layout = QHBoxLayout(variant_row_widget)
        row_layout.setContentsMargins(5, 5, 5, 5)

        details_layout = QVBoxLayout()
        details_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addLayout(details_layout)

        # --- Atrybuty <variant> ---
        attributes_layout = QGridLayout()
        attributes_layout.setContentsMargins(0, 0, 0, 5)
        details_layout.addLayout(attributes_layout)
        attr_row = 0
        attribute_widgets = {}
        if var_element.attrib:
            # print(f"        Adding variant attributes:") # DEBUG
            for key, value in sorted(var_element.attrib.items()):
                # print(f"          '{key}': '{value}'") # DEBUG
                attr_label = QLabel(f"{key}:")
                attr_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)

                attr_input = QLineEdit(value)
                attr_input.setObjectName(f"input_variant_{key}_{id(var_element)}")

                # Dodaj widgety do layoutu *przed* dołączeniem kompletera
                attributes_layout.addWidget(attr_label, attr_row, 0)
                attributes_layout.addWidget(attr_input, attr_row, 1)

                # Dołącz QCompleter
                if key == 'category':
                    self._attach_completer(attr_input, self.item_category_model)
                elif key == 'equip_template':
                    self._attach_completer(attr_input, self.equip_template_model)

                # Połącz sygnały
                try:
                    attr_input.editingFinished.disconnect()
                except RuntimeError:
                    pass
                attr_input.editingFinished.connect(
                    lambda k=key, i=attr_input, elem=var_element: self.variant_attribute_changed(elem, k, i.text()))

                attribute_widgets[key] = attr_input
                attr_row += 1
        # else: print("        No attributes found on <variant>.") # DEBUG

        # Przycisk dodawania atrybutu do wariantu
        add_variant_attr_button = QPushButton("+ Variant attribute")
        add_variant_attr_button.setToolTip("Add a new attribute to this variant")
        try:
            add_variant_attr_button.clicked.disconnect()
        except RuntimeError:
            pass
        add_variant_attr_button.clicked.connect(
            lambda elem=var_element, r_widget=variant_row_widget: self.add_variant_attribute(elem, r_widget))
        attributes_layout.addWidget(add_variant_attr_button, attr_row, 0, 1, 2)
        # --- Koniec Atrybutów ---


        # --- Zagnieżdżone Elementy ---
        nested_items_layout = None
        all_children = list(var_element)
        nested_element_children = [child for child in all_children if ET.iselement(child)]

        # print(f"        Checking nested children. Found: {len(nested_element_children)} element(s). Total children: {len(all_children)}") # DEBUG
        if nested_element_children:
            nested_label = QLabel("Elementy Zagnieżdżone:")
            font = nested_label.font()
            font.setItalic(True)
            nested_label.setFont(font)
            details_layout.addWidget(nested_label)

            nested_items_layout = QVBoxLayout()
            nested_items_layout.setObjectName(f"NestedItemsLayout_{id(var_element)}")
            nested_items_layout.setContentsMargins(15, 2, 0, 2)
            details_layout.addLayout(nested_items_layout)

            # --- ITERUJ PO WSZYSTKICH DZIECIACH, ALE SPRAWDZAJ TYP PRZED WYWOŁANIEM ---
            print(f"        Przetwarzanie {len(all_children)} dzieci wariantu (w tym komentarzy)...") # DEBUG
            for child_node in all_children: # Iteruj po oryginalnej liście dzieci
                if ET.iselement(child_node): # *** KLUCZOWE SPRAWDZENIE BEZPOŚREDNIO TUTAJ ***
                    # Wywołaj funkcję tylko dla rzeczywistych elementów XML
                    # print(f"          Processing nested element: <{child_node.tag}> Text='{child_node.text}'") # DEBUG
                    self.add_nested_variant_item_widget(child_node, var_element, nested_items_layout)
                # else: # Opcjonalnie loguj pomijane węzły
                #    print(f"          INFO [add_variant_widget]: Ignorowanie węzła niebędącego elementem: {repr(child_node)}")
            # --- KONIEC POPRAWIONEJ PĘTLI ---
            # print(f"          Zakończono dodawanie widgetów zagnieżdżonych. layout count: {nested_items_layout.count()}") # DEBUG

            add_nested_item_button = QPushButton("+ Add Nested Element")
            add_nested_item_button.setToolTip("Add a new element (e.g. <item>) inside this variant")
            try:
                add_nested_item_button.clicked.disconnect()
            except RuntimeError:
                pass
            # Upewnij się, że nested_items_layout nie jest None, jeśli są dzieci
            if nested_items_layout:
                 add_nested_item_button.clicked.connect(
                     lambda v_elem=var_element, layout=nested_items_layout: self.add_nested_variant_item(v_elem, layout))
                 details_layout.addWidget(add_nested_item_button, alignment=Qt.AlignLeft)
            else:
                 # To nie powinno się zdarzyć, jeśli nested_element_children nie jest puste
                 print("OSTRZEŻENIE: nested_items_layout jest None mimo istnienia dzieci elementów.")

        # --- Koniec Zagnieżdżonych Elementów ---


        # --- Główny Przycisk Usuwania dla całego wariantu ---
        remove_button = QPushButton("X")
        remove_button.setFixedWidth(30)
        remove_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        remove_button.setToolTip(f"Usuń cały ten wariant")
        try:
            remove_button.clicked.disconnect()
        except RuntimeError:
            pass
        remove_button.clicked.connect(lambda w=variant_row_widget, elem=var_element: self.remove_list_widget(
            w, elem, 'variants', self.variants_layout))
        # Dodaj przycisk do głównego layoutu poziomego, wyrównany do góry
        row_layout.addWidget(remove_button, alignment=Qt.AlignTop)
        # --- Koniec Przycisku Usuwania ---

        # Dodaj cały widget wiersza do głównego layoutu sekcji wariantów (self.variants_layout)
        self.variants_layout.addWidget(variant_row_widget)
        # print(f"      -> self.variants_layout count is now: {self.variants_layout.count()}") # DEBUG count check

# ... inside WitcherXMLEditor add_variant_attribute ...
    def add_variant_attribute(self, variant_element, variant_row_widget):
         if self._populating_details: return
         # Use configured dialog to allow completer for attribute name
         dialog = QInputDialog(self)
         dialog.setWindowTitle("Add Variant Attribute")
         dialog.setLabelText("Name of the new attribute for <variant>:")
         dialog.setInputMode(QInputDialog.InputMode.TextInput)
         line_edit = dialog.findChild(QLineEdit)
         if line_edit:
             # Suggest existing variant attribute names
             self._attach_completer(line_edit, self.variant_attribute_name_model)
         else: print("Warning: Could not find QLineEdit in Add Variant Attribute dialog.")

         if dialog.exec() == QDialog.DialogCode.Accepted:
            attr_name = dialog.textValue().strip().replace(" ", "_");
            # ... (rest of validation and adding logic) ...

# ... inside WitcherXMLEditor add_nested_variant_item ...
    def add_nested_variant_item(self, variant_element, nested_items_layout):
        if self._populating_details: return
        # --- Dialog for Tag Name ---
        tag_dialog = QInputDialog(self)
        tag_dialog.setWindowTitle("Dodaj Element Zagnieżdżony - Tag")
        tag_dialog.setLabelText("Nazwa tagu (np. 'item'):")
        tag_dialog.setInputMode(QInputDialog.InputMode.TextInput)
        tag_dialog.setTextValue("item") # Default
        tag_line_edit = tag_dialog.findChild(QLineEdit)
        if tag_line_edit:
             # Suggest existing nested tags
             self._attach_completer(tag_line_edit, self.variant_nested_tag_model)
        else: print("Warning: Could not find QLineEdit in Add Nested Tag dialog.")

        if tag_dialog.exec() != QDialog.DialogCode.Accepted: return
        tag_name = tag_dialog.textValue().strip().replace(" ", "_")
        if not tag_name: return

        # --- Dialog for Text Value ---
        text_dialog = QInputDialog(self)
        text_dialog.setWindowTitle("Dodaj Element Zagnieżdżony - Tekst")
        text_dialog.setLabelText(f"Tekst dla <{tag_name}>:")
        text_dialog.setInputMode(QInputDialog.InputMode.TextInput)
        text_line_edit = text_dialog.findChild(QLineEdit)
        if text_line_edit:
             # Suggest items or abilities based on tag name
             if tag_name.lower() == 'item':
                 self._attach_completer(text_line_edit, self.item_name_model)
             elif tag_name.lower() == 'ability':
                  self._attach_completer(text_line_edit, self.ability_name_model)
        else: print("Warning: Could not find QLineEdit in Add Nested Text dialog.")

        if text_dialog.exec() != QDialog.DialogCode.Accepted: return
        text_value = text_dialog.textValue().strip()

        # --- Add to XML and UI ---
        new_child = ET.SubElement(variant_element, tag_name); new_child.text = text_value
        self.mark_file_modified(self.current_selection_filepath)
        self.add_nested_variant_item_widget(new_child, variant_element, nested_items_layout)
        # Update model for nested tags if it's a new tag
        if tag_name not in self.all_variant_nested_tags:
             self.all_variant_nested_tags.add(tag_name)
             self.variant_nested_tag_model.setStringList(sorted(list(self.all_variant_nested_tags)))
        print(f"Added nested element <{tag_name}> to variant.")


    def populate_item_details(self, element, file_path):
        """Wypełnia sekcje prawego panelu specyficzne dla Przedmiotów (Items)."""
        print(f"===== Rozpoczynanie populate_item_details dla: {element.get('name')} =====")
        item_category_value = element.get('category', 'N/A'); print(f"  Kategoria: '{item_category_value}'")

        # --- Wypełnij Atrybuty Przedmiotu (<item ... />) ---
        print("--- Wypełnianie Atrybutów Przedmiotu ---")
        self.clear_layout(self.item_attributes_layout)
        row = 0
        for key, value in sorted(element.attrib.items()):
             if key == 'name': continue
             attr_label = QLabel(f"{key}:")
             attr_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
             attr_input = QLineEdit(value)
             attr_input.setObjectName(f"input_{key}")

             # NAJPIERW DODAJ WIDGETY DO LAYOUTU
             self.item_attributes_layout.addWidget(attr_label, row, 0)
             self.item_attributes_layout.addWidget(attr_input, row, 1)

             # --- DOPIERO TERAZ DOŁĄCZ QCOMPLETER ---
             # print(f"    Sprawdzanie atrybutu '{key}' pod kątem kompletera...") # DEBUG
             if key == 'category': self._attach_completer(attr_input, self.item_category_model)
             elif key == 'ability_mode': self._attach_completer(attr_input, self.ability_mode_model)
             elif key == 'equip_template': self._attach_completer(attr_input, self.equip_template_model)
             elif key == 'equip_slot': self._attach_completer(attr_input, self.equip_slot_model)
             elif key == 'hold_slot': self._attach_completer(attr_input, self.hold_slot_model) # <-- Dodany
             elif key == 'hand': self._attach_completer(attr_input, self.hand_model)           # <-- Dodany
             elif key == 'sound_identification': self._attach_completer(attr_input, self.sound_id_model) # <-- Dodany
             elif key in ['draw_event', 'holster_event']: self._attach_completer(attr_input, self.event_model) # <-- Dodany
             elif key in ['draw_act', 'draw_deact', 'holster_act', 'holster_deact']: self._attach_completer(attr_input, self.anim_action_model) # <-- Używa anim_action_model
             elif key == 'enhancement_slots': self._attach_completer(attr_input, self.enhancement_slots_model)
             elif key in ['weapon', 'lethal']: self._attach_completer(attr_input, self.boolean_value_model)
             elif key.startswith('localisation_key'): self._attach_completer(attr_input, self.localisation_key_model)
             elif key == 'icon_path': self._attach_completer(attr_input, self.icon_path_model)
             # --- Koniec Dołączania QCompleter ---

             # Łączenie sygnałów
             try: attr_input.editingFinished.disconnect()
             except RuntimeError: pass
             attr_input.editingFinished.connect(lambda k=key, i=attr_input: self.item_attribute_changed(k, i.text()))

             row += 1

        # Przycisk "+ Atrybut Elementu"
        add_item_attr_button = QPushButton("+ Element attribute")
        try: add_item_attr_button.clicked.disconnect()
        except RuntimeError: pass
        add_item_attr_button.clicked.connect(self.add_item_attribute)
        self.item_attributes_layout.addWidget(add_item_attr_button, row, 0, 1, 2)
        print("--- Zakończono Atrybuty Przedmiotu ---")

        # --- Wypełnij Bazowe Umiejętności ---
        print("--- Rozpoczynanie Bazowych Umiejętności ---")
        self.clear_layout(self.base_abilities_layout)
        base_abilities_node = element.find('base_abilities')
        if base_abilities_node is not None:
             children = base_abilities_node.findall('a')
             # print(f"  Znaleziono {len(children)} elementów <a>.") # DEBUG
             for i, ab_element in enumerate(children):
                 # print(f"    >>> Pętla Base Abilities - Iteracja {i+1}") # DEBUG
                 self.add_base_ability_widget(ab_element)
             # print("  Zakończono pętlę Base Abilities.") # DEBUG
        # else: print("  Węzeł <base_abilities> NIE znaleziony.")
        print("--- Zakończono Bazowe Umiejętności ---")

        # --- Wypełnij Części do Recyklingu ---
        print("--- Rozpoczynanie Części do Recyklingu ---")
        self.clear_layout(self.recycling_parts_layout)
        recycling_parts_node = element.find('recycling_parts')
        if recycling_parts_node is not None:
             children = recycling_parts_node.findall('parts')
             # print(f"  Znaleziono {len(children)} elementów <parts>.") # DEBUG
             for i, part_element in enumerate(children):
                 # print(f"    >>> Pętla Recycling Parts - Iteracja {i+1}") # DEBUG
                 self.add_recycling_part_widget(part_element)
             # print("  Zakończono pętlę Recycling Parts.") # DEBUG
        # else: print("  Węzeł <recycling_parts> NIE znaleziony.")
        print("--- Zakończono Części do Recyklingu ---")

        # --- Wypełnij Warianty ---
        print("--- Rozpoczynanie Wariantów ---")
        self.clear_layout(self.variants_layout)
        variants_node = element.find('variants')
        if variants_node is not None:
             variant_children = variants_node.findall('variant')
             # print(f"  Znaleziono {len(variant_children)} elementów <variant>.") # DEBUG
             for i, var_element in enumerate(variant_children):
                 # print(f"    Przetwarzanie <variant> #{i+1}: Atrybuty={var_element.attrib}") # DEBUG
                 self.add_variant_widget(var_element)
             # print(f"  Zakończono warianty. Liczba widgetów w variants_layout: {self.variants_layout.count()}") # DEBUG
        # else: print("  Węzeł <variants> NIE znaleziony.")
        print("--- Zakończono Warianty ---")

        print(f"===== Zakończono populate_item_details dla: {element.get('name')} =====")
    def populate_ability_details(self, element, file_path):
        print(f"--- Populating Ability details for: {element.get('name')} ---") # DEBUG
        self.clear_layout(self.properties_layout) # Clear previous properties
        ignored_tags = {'tags'}
        prop_count = 0
        for child in element:
            if child.tag not in ignored_tags:
                prop_widget = PropertyWidget(child, file_path, self)
                self.properties_layout.addWidget(prop_widget)
                prop_count += 1
        print(f"  Added {prop_count} property widgets.") # DEBUG


    # --- Widget Add/Remove Helpers for Item Sections ---




    def remove_list_widget(self, widget_to_remove, element_to_remove, parent_tag, layout):
        """Removes a widget and its corresponding XML element from a list section."""
        if self._populating_details or not self.current_selection_element: return
        parent_node = self.current_selection_element.find(parent_tag)
        if parent_node is not None:
            # No confirmation needed? Or add it back? Let's remove confirmation for smoother edits.
            # confirm = QMessageBox.question(...)
            # if confirm == QMessageBox.StandardButton.Yes:
            try:
                parent_node.remove(element_to_remove)
                self.mark_file_modified(self.current_selection_filepath)
                widget_to_remove.deleteLater()
                print(f"Removed element <{element_to_remove.tag}> from {parent_tag}")
            except ValueError: print(f"Error: Element not found in {parent_tag} during removal.")
            except Exception as e: print(f"Error removing list widget: {e}")


    # --- Editing Actions Handlers ---
    def tags_changed(self): # ... (Logic same, ensure flag check) ...
        if self._populating_details or not self.current_selection_element: return
        new_tags_text = self.tags_input.text().strip(); tags_element = self.current_selection_element.find('tags')
        current_text = tags_element.text.strip() if tags_element is not None and tags_element.text else ""
        if new_tags_text == current_text: return
        if tags_element is None:
            if new_tags_text: tags_element = ET.SubElement(self.current_selection_element, 'tags'); tags_element.text = new_tags_text; self.mark_file_modified(self.current_selection_filepath); print(f"Added tags: {new_tags_text}")
        elif new_tags_text: tags_element.text = new_tags_text; self.mark_file_modified(self.current_selection_filepath); print(f"Updated tags: {new_tags_text}")
        else: self.current_selection_element.remove(tags_element); self.mark_file_modified(self.current_selection_filepath); print(f"Removed empty tags element.")
        self.all_tags.update(t.strip() for t in new_tags_text.split(',') if t.strip())

    def item_attribute_changed(self, attr_name, new_value): # ... (Logic same, ensure flag check) ...
        if self._populating_details or not self.current_selection_element: return
        old_value = self.current_selection_element.get(attr_name)
        if old_value != new_value: self.current_selection_element.set(attr_name, new_value); self.mark_file_modified(self.current_selection_filepath); print(f"Item attribute '{attr_name}' changed to '{new_value}'")

    def base_ability_text_changed(self, ab_element, new_text): # ... (Logic same, ensure flag check) ...
        if self._populating_details: return
        new_text = new_text.strip(); current_text = ab_element.text.strip() if ab_element.text else ""
        if current_text != new_text: ab_element.text = new_text; self.mark_file_modified(self.current_selection_filepath); print(f"Base ability text changed to '{new_text}'")

    def part_attribute_changed(self, part_element, attr_name, new_value): # ... (Logic same, ensure flag check) ...
        if self._populating_details: return
        new_value = new_value.strip()
        if part_element.get(attr_name) != new_value: part_element.set(attr_name, new_value); self.mark_file_modified(self.current_selection_filepath); print(f"Recycling part attr '{attr_name}' changed to '{new_value}'")

    def part_text_changed(self, part_element, new_text): # ... (Logic same, ensure flag check) ...
        if self._populating_details: return
        new_text = new_text.strip(); current_text = part_element.text.strip() if part_element.text else ""
        if current_text != new_text: part_element.text = new_text; self.mark_file_modified(self.current_selection_filepath); print(f"Recycling part name changed to '{new_text}'")

    def variant_attribute_changed(self, var_element, attr_name, new_value): # ... (Logic same, ensure flag check) ...
         if self._populating_details: return
         new_value = new_value.strip()
         if var_element.get(attr_name) != new_value: var_element.set(attr_name, new_value); self.mark_file_modified(self.current_selection_filepath); print(f"Variant attr '{attr_name}' changed to '{new_value}'")

    def nested_variant_item_text_changed(self, child_element, new_text): # ... (Logic same, ensure flag check) ...
        if self._populating_details: return
        new_text = new_text.strip(); current_text = child_element.text.strip() if child_element.text else ""
        if current_text != new_text: child_element.text = new_text; self.mark_file_modified(self.current_selection_filepath); print(f"Nested variant item <{child_element.tag}> text changed to '{new_text}'")

    # --- Add Buttons for Item Sections ---
    def add_element_to_section(self, parent_tag_name, child_tag_name, add_widget_func, default_attrs=None):
         if self._populating_details or not self.current_selection_element: return
         parent_node = self.current_selection_element.find(parent_tag_name)
         if parent_node is None: parent_node = ET.SubElement(self.current_selection_element, parent_tag_name); print(f"Created parent node <{parent_tag_name}>")
         new_child = ET.SubElement(parent_node, child_tag_name)
         if default_attrs: # Set default attributes if provided
             for k, v in default_attrs.items(): new_child.set(k, v)
         add_widget_func(new_child) # Add the UI widget
         self.mark_file_modified(self.current_selection_filepath)
         print(f"Added new <{child_tag_name}> to <{parent_tag_name}>")

    def add_base_ability(self): self.add_element_to_section('base_abilities', 'a', self.add_base_ability_widget)
    def add_recycling_part(self): self.add_element_to_section('recycling_parts', 'parts', self.add_recycling_part_widget, default_attrs={'count': '1'})
    def add_variant(self): self.add_element_to_section('variants', 'variant', self.add_variant_widget, default_attrs={'category': 'DefaultCategory', 'equip_template': 'DefaultTemplate'}) # Add defaults

    def add_item_attribute(self):
         if self._populating_details or not self.current_selection_element: return
         attr_name, ok = QInputDialog.getText(self, "Add Element Attribute", "The name of the new attribute for <item>:");
         if ok and attr_name:
             attr_name = attr_name.strip().replace(" ", "_");
             if not attr_name: QMessageBox.warning(self, "Error", "Nazwa pusta."); return
             if attr_name in self.current_selection_element.attrib: QMessageBox.warning(self, "Error", f"Atrybut '{attr_name}' już istnieje."); return
             self.current_selection_element.set(attr_name, ""); self.mark_file_modified(self.current_selection_filepath)
             self.all_attribute_names.add(attr_name); self.populate_item_details(self.current_selection_element, self.current_selection_filepath); # Refresh UI section
             print(f"Added item attribute '{attr_name}'")

    def add_variant_attribute(self, variant_element, variant_row_widget):
         # ... (same logic as before, ensure flag check) ...
         if self._populating_details: return
         attr_name, ok = QInputDialog.getText(self, "Add Variant Attribute", "The name of the new attribute for <variant>:")
         if ok and attr_name:
             attr_name = attr_name.strip().replace(" ", "_");
             if not attr_name: return
             if attr_name in variant_element.attrib: QMessageBox.warning(self, "Error", f"Atrybut '{attr_name}' już istnieje."); return
             variant_element.set(attr_name, ""); self.mark_file_modified(self.current_selection_filepath); self.all_attribute_names.add(attr_name)
             # Dynamically update UI (find grid, insert before button)
             grid_layout = variant_row_widget.findChild(QGridLayout);
             if grid_layout:
                  add_button_widget = None
                  # Find the add button widget *within* the loop
                  for i in range(grid_layout.count()):
                       widget_item = grid_layout.itemAt(i)
                       if widget_item is None: continue # Skip if item is None
                       widget = widget_item.widget();
                       if isinstance(widget, QPushButton) and "+" in widget.text():
                           add_button_widget = widget
                           break # <<< CORRECT PLACEMENT: Break *inside* the if, *inside* the loop
                  # Now proceed using add_button_widget found (or not found)
                  if add_button_widget:
                       button_row, _, _, _ = grid_layout.getItemPosition(grid_layout.indexOf(add_button_widget))
                       attr_label = QLabel(f"{attr_name}:"); attr_input = QLineEdit("")
                       attr_input.editingFinished.connect(lambda k=attr_name, i=attr_input, elem=variant_element: self.variant_attribute_changed(elem, k, i.text()))
                       grid_layout.addWidget(attr_label, button_row, 0); grid_layout.addWidget(attr_input, button_row, 1)
                       grid_layout.addWidget(add_button_widget, button_row + 1, 0, 1, 2); print(f"Added attribute '{attr_name}' to variant UI.")
                  else: print("Error: Could not find add attribute button in variant widget.")
             else: print("Error: Could not find QGridLayout in variant widget.")

    def add_nested_variant_item(self, variant_element, nested_items_layout):
        # ... (same logic as before, ensure flag check) ...
        if self._populating_details: return
        tag_name, ok1 = QInputDialog.getText(self, "Add Armor Variants", "Tag name (e.g. 'item'):", text="item")
        if not (ok1 and tag_name): return
        tag_name = tag_name.strip().replace(" ", "_")
        text_value, ok2 = QInputDialog.getText(self, "Add Armor Variants", f"Text for <{tag_name}>:")
        if not ok2: return
        new_child = ET.SubElement(variant_element, tag_name); new_child.text = text_value.strip()
        self.mark_file_modified(self.current_selection_filepath)
        self.add_nested_variant_item_widget(new_child, variant_element, nested_items_layout)
        print(f"Added nested element <{tag_name}> to variant.")

    def remove_nested_variant_item(self, widget_to_remove, element_to_remove, parent_variant_element):
        # ... (same logic as before, ensure flag check) ...
        if self._populating_details: return
        try: parent_variant_element.remove(element_to_remove); self.mark_file_modified(self.current_selection_filepath); widget_to_remove.deleteLater(); print(f"Removed nested element <{element_to_remove.tag}> from variant.")
        except ValueError: print(f"Error: Element <{element_to_remove.tag}> not found in parent variant during removal.")
        except Exception as e: print(f"Error removing nested variant item widget: {e}")

    def add_property(self): # Dla Abilities
        if self._populating_details or not self.current_selection_element:
            QMessageBox.warning(self, "Error", "First select an element (Ability).")
            return
        if self.current_selection_type != 'ability':
            QMessageBox.information(self, "Information", "This option is only for the 'Ability' type.")
            return

        # --- Utwórz i skonfiguruj instancję QInputDialog ---
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Add Ability")
        dialog.setLabelText("Enter the name of the new property (e.g. 'stamina'):")
        dialog.setInputMode(QInputDialog.InputMode.TextInput)
        line_edit = dialog.findChild(QLineEdit)

        if line_edit:
            # Dołącz model z nazwami istniejących właściwości
            # Używamy property_name_model, który powinien zawierać tylko stringi (po load_xml_files)
            self._attach_completer(line_edit, self.property_name_model)
            print("Completer (property names) attached to QInputDialog.")
        else:
            print("Warning: Could not find QLineEdit in QInputDialog to attach completer.")

        # --- Wykonaj dialog i przetwórz wynik ---
        if dialog.exec() == QDialog.DialogCode.Accepted:
            prop_name = dialog.textValue().strip()
            if not prop_name:
                QMessageBox.warning(self, "Error", "Property name blank."); return
            if prop_name in self.known_item_child_tags:
                 QMessageBox.warning(self, "Error", f"'{prop_name}' jest zarezerwowaną nazwą sekcji Item."); return
            if self.current_selection_element.find(prop_name) is not None:
                 QMessageBox.warning(self, "Error", f"Właściwość '{prop_name}' już istnieje."); return

            # --- Dodaj element i zaktualizuj UI ---
            print(f"Adding property '{prop_name}' to ability '{self.current_selection_name}'")
            new_element = ET.SubElement(self.current_selection_element, prop_name)
            new_element.set('type', 'add'); new_element.set('min', '0') # Domyślne atrybuty

            self.mark_file_modified(self.current_selection_filepath)

            # --- POPRAWIONA AKTUALIZACJA MODELU ---
            # Zaktualizuj zbiór i model, jeśli to nowa nazwa właściwości
            if prop_name not in self.all_property_names:
                self.all_property_names.add(prop_name)
                # Użyj bezpiecznej funkcji sortującej, aby zaktualizować model
                # Zakładamy, że safe_sorted_string_list jest dostępna (np. zdefiniowana w load_xml_files
                # lub jako metoda klasy, co byłoby lepsze)
                # Na razie skopiujemy jej logikę tutaj dla prostoty:
                string_list = []
                for item in self.all_property_names:
                    if isinstance(item, str):
                        string_list.append(item)
                    else:
                         # Można dodać logowanie jak w load_xml_files, jeśli chcemy wiedzieć, co jest pomijane
                         print(f"OSTRZEŻENIE (add_property): Pomijanie elementu niebędącego stringiem w all_property_names: {repr(item)}")
                try:
                    self.property_name_model.setStringList(sorted(string_list))
                except TypeError as e_sort:
                     print(f"KRYTYCZNY BŁĄD SORTOWANIA w add_property dla property_name_model: {e_sort}")
                     self.property_name_model.setStringList(string_list) # Ustaw niesortowaną
            # --- KONIEC POPRAWIONEJ AKTUALIZACJI ---

            # Zaktualizuj też zbiór i model atrybutów właściwości
            self.all_property_attribute_names.update(['type', 'min'])
            # Tutaj też można by użyć bezpiecznego sortowania, ale zazwyczaj dodajemy znane stringi
            try:
                 prop_attr_list = sorted(list(self.all_property_attribute_names))
                 self.property_attribute_name_model.setStringList(prop_attr_list)
            except TypeError as e: print(f"BŁĄD sortowania property_attribute_name_model w add_property: {e}")


            # Dodaj widget do UI
            prop_widget = PropertyWidget(new_element, self.current_selection_filepath, self)
            self.properties_layout.addWidget(prop_widget)
            if not self.properties_section.isVisible(): self.set_ability_specific_visibility(True)
            print(f"Added property UI widget for: {prop_name}")

    def add_entry(self):
        if self._populating_details: return # Prevent action during UI population

        # Sprawdź, czy są załadowane jakiekolwiek pliki
        if not self.loaded_files:
            QMessageBox.warning(self, "Error", "No XML files were uploaded. Open folder with xml files.")
            return

        current_tab_index = self.tab_widget.currentIndex()
        entry_type = 'ability' if current_tab_index == 0 else 'item'
        data_map = self.abilities_map if entry_type == 'ability' else self.items_map
        list_widget = self.ability_list if entry_type == 'ability' else self.item_list

        new_name, ok = QInputDialog.getText(self, f"Dodaj {entry_type.capitalize()}", f"Nazwa nowego {entry_type}:")

        if ok and new_name:
            new_name = new_name.strip()
            if not new_name:
                QMessageBox.warning(self, "Error", "The name must not be empty."); return
            if new_name in data_map:
                QMessageBox.warning(self, "Error", f"{entry_type.capitalize()} '{new_name}' already exists."); return

            # --- Ustalanie Pliku Docelowego i Węzła Rodzica ---
            target_filepath = None
            parent_node = None
            parent_node_tag = 'abilities' if entry_type == 'ability' else 'items'
            root_to_modify = None

            # 1. Sprawdź, czy coś jest aktualnie zaznaczone
            if self.current_selection_filepath and self.current_selection_filepath in self.loaded_files:
                target_filepath = self.current_selection_filepath
                root_to_modify = self.loaded_files[target_filepath]['root']
                print(f"Priorytet: Dodawanie do pliku aktywnego elementu: {target_filepath}")

                # Szukaj węzła rodzica TYLKO w tym pliku
                # Najpierw szukaj w <definitions>
                definitions_node = root_to_modify.find('definitions')
                if definitions_node is not None:
                    parent_node = definitions_node.find(parent_node_tag)

                # Jeśli nie ma w <definitions>, szukaj bezpośrednio pod root (mniej typowe, ale możliwe)
                if parent_node is None:
                     parent_node = root_to_modify.find(parent_node_tag) # Bez .// aby szukać tylko bezpośrednich dzieci root

                # Jeśli węzeł rodzica nadal nie istnieje w TYM pliku, stwórz go
                if parent_node is None:
                    print(f"Węzeł <{parent_node_tag}> nie istnieje w {target_filepath}. Tworzenie struktury...")
                    # Upewnij się, że istnieje <definitions>
                    if definitions_node is None:
                         definitions_node = ET.SubElement(root_to_modify, 'definitions')
                         print("  Stworzono <definitions>.")
                    # Stwórz węzeł rodzica wewnątrz <definitions>
                    parent_node = ET.SubElement(definitions_node, parent_node_tag)
                    print(f"  Stworzono <{parent_node_tag}> wewnątrz <definitions>.")

            # 2. Fallback - jeśli nic nie jest zaznaczone
            else:
                print("INFO: Brak aktywnego elementu. Szukanie odpowiedniego pliku (fallback)...")
                # Szukaj pierwszego pliku, który zawiera odpowiedni węzeł
                for fp, data in self.loaded_files.items():
                    root = data['root']
                    # Szukaj .// aby znaleźć gdziekolwiek
                    found_node = root.find(f".//{parent_node_tag}")
                    if found_node is not None:
                        target_filepath = fp
                        parent_node = found_node
                        root_to_modify = root # Zapamiętaj root tego pliku
                        print(f"  Fallback: Znaleziono węzeł <{parent_node_tag}> w pliku: {fp}")
                        break # Użyj pierwszego znalezionego

                # Jeśli nadal nie znaleziono, stwórz w PIERWSZYM załadowanym pliku
                if parent_node is None:
                     target_filepath = next(iter(self.loaded_files)) # Weź pierwszy plik z listy
                     root_to_modify = self.loaded_files[target_filepath]['root']
                     print(f"  Fallback: Brak węzła <{parent_node_tag}> w żadnym pliku. Tworzenie w pierwszym pliku: {target_filepath}")
                     definitions_node = root_to_modify.find('definitions')
                     if definitions_node is None:
                         definitions_node = ET.SubElement(root_to_modify, 'definitions')
                         print("    Stworzono <definitions>.")
                     parent_node = definitions_node.find(parent_node_tag) # Sprawdź jeszcze raz w definitions
                     if parent_node is None:
                         parent_node = ET.SubElement(definitions_node, parent_node_tag) # Stwórz w definitions
                         print(f"    Stworzono <{parent_node_tag}> wewnątrz <definitions>.")

            # --- Koniec Ustalania Pliku Docelowego ---

            # Jeśli z jakiegoś powodu nie udało się ustalić parent_node (nie powinno się zdarzyć po powyższej logice)
            if parent_node is None or target_filepath is None:
                 QMessageBox.critical(self, "Błąd Krytyczny", "Nie udało się znaleźć ani stworzyć odpowiedniego węzła rodzica w plikach XML.")
                 return

            # --- Utwórz nowy element i dodaj domyślną strukturę ---
            print(f"Dodawanie nowego elementu <{entry_type}> z nazwą '{new_name}' do pliku {target_filepath}...")
            new_element = ET.SubElement(parent_node, entry_type)
            new_element.set('name', new_name)
            ET.SubElement(new_element, 'tags') # Dodaj pusty element tags

            if entry_type == 'item':
                # Dodaj domyślne atrybuty i puste struktury dla item
                new_element.set('category', 'misc') # Przykładowe domyślne
                new_element.set('price', '1')
                ET.SubElement(new_element, 'base_abilities')
                ET.SubElement(new_element, 'recycling_parts')
                ET.SubElement(new_element, 'variants')
            # --- Koniec Tworzenia Elementu ---

            # --- Zaktualizuj struktury danych i UI ---
            # Dodaj do mapy, wskazując poprawny plik
            data_map[new_name] = {'filepath': target_filepath, 'element': new_element}
            # Dodaj do listy UI
            list_widget.addItem(QListWidgetItem(new_name))
            list_widget.sortItems()

            # Zaznacz nowo dodany element w liście
            items = list_widget.findItems(new_name, Qt.MatchExactly);
            if items:
                list_widget.setCurrentItem(items[0]) # Zaznaczenie wywoła populate_details
                print(f"Zaznaczono nowy element '{new_name}' w liście.")
            else:
                print(f"OSTRZEŻENIE: Nie znaleziono elementu '{new_name}' w liście po dodaniu.")

            # Oznacz plik jako zmodyfikowany
            self.mark_file_modified(target_filepath)
            print(f"Dodano nowy {entry_type}: {new_name} do {target_filepath}")
            self.statusBar.showMessage(f"Dodano: {new_name}", 3000)
            # --- Koniec Aktualizacji ---

        elif ok and not new_name.strip():
            QMessageBox.warning(self, "Error", "Nazwa nie może być pusta.")
        # else: # Anulowano dialog
        #    pass

    def remove_entry(self): # ... (Same logic, ensure flag check) ...
        if self._populating_details or not self.current_selection_element:
            QMessageBox.warning(self, "Error", "Select an element."); return

        entry_type = self.current_selection_type; name = self.current_selection_name
        element = self.current_selection_element; file_path = self.current_selection_filepath
        data_map = self.abilities_map if entry_type == 'ability' else self.items_map
        list_widget = self.ability_list if entry_type == 'ability' else self.item_list

        confirm = QMessageBox.question(self, f"Usuń {entry_type.capitalize()}", f"Czy na pewno chcesz usunąć '{name}'?")

        if confirm == QMessageBox.StandardButton.Yes:
            parent_element = self.get_parent_element(element, file_path);
            if parent_element is not None:
                try:
                    # Actions to perform if parent is found
                    parent_element.remove(element)
                    self.mark_file_modified(file_path)
                    del data_map[name] # Remove from internal tracking

                    # Remove from UI list
                    items = list_widget.findItems(name, Qt.MatchExactly);
                    if items:
                        row = list_widget.row(items[0])
                        list_widget.takeItem(row)

                    self.clear_details_pane() # Clear the right pane
                    print(f"Removed {entry_type}: {name}")
                    self.statusBar.showMessage(f"Usunięto: {name}", 3000)

                except ValueError: # <<< Correct indentation for except
                    print(f"Error: Element '{name}' not found in parent during remove attempt.");
                    QMessageBox.critical(self, "Błąd Wew.", f"Nie można znaleźć elementu '{name}' w strukturze XML do usunięcia (ValueError).")
                except Exception as e: # <<< Correct indentation for except
                    print(f"Error removing: {e}");
                    QMessageBox.critical(self, "Błąd Usuwania", f"Wystąpił błąd podczas usuwania '{name}':\n{e}")
            else:
                # Error if parent wasn't found in the first place
                print(f"Error: Could not find parent for '{name}' using get_parent_element.");
                QMessageBox.critical(self, "Błąd Wew.", f"Nie można znaleźć rodzica dla elementu '{name}' w pliku.")

    def duplicate_entry(self): # ... (Same logic, ensure flag check) ...
            if self._populating_details or not self.current_selection_element: QMessageBox.warning(self, "Error", "Select an element."); return
            original_name = self.current_selection_name; original_element = self.current_selection_element; original_filepath = self.current_selection_filepath
            entry_type = self.current_selection_type; data_map = self.abilities_map if entry_type == 'ability' else self.items_map
            list_widget = self.ability_list if entry_type == 'ability' else self.item_list

            new_name, ok = QInputDialog.getText(self, f"Duplikuj {entry_type.capitalize()}", f"Nowa nazwa dla kopii '{original_name}':", text=f"{original_name}_copy")

            if ok and new_name:
                new_name = new_name.strip();
                if not new_name:
                    QMessageBox.warning(self, "Error", "Nazwa pusta."); return
                if new_name in data_map:
                    QMessageBox.warning(self, "Error", f"Nazwa '{new_name}' już istnieje."); return

                parent_element = self.get_parent_element(original_element, original_filepath);
                if parent_element is not None: # <<< Correct IF alignment
                    try:
                        new_element = copy.deepcopy(original_element); new_element.set('name', new_name)
                        # --- Insertion Logic ---
                        parent_list = list(parent_element);
                        try:
                            original_index = parent_list.index(original_element)
                            parent_element.insert(original_index + 1, new_element) # Separated line
                        except ValueError:
                            parent_element.append(new_element) # Append if index fails
                        # --- End Insertion Logic ---

                        # Update data map and UI
                        data_map[new_name] = {'filepath': original_filepath, 'element': new_element};
                        list_widget.addItem(QListWidgetItem(new_name)); list_widget.sortItems()
                        items = list_widget.findItems(new_name, Qt.MatchExactly);
                        if items: list_widget.setCurrentItem(items[0]) # Select new item

                        self.mark_file_modified(original_filepath);
                        print(f"Duplicated '{original_name}' as '{new_name}'");
                        self.statusBar.showMessage(f"Zduplikowano jako: {new_name}", 3000)

                    except Exception as e: # Catch errors during deepcopy or UI update
                        print(f"Error duplicating: {e}");
                        QMessageBox.critical(self, "Błąd Duplikowania", f"Błąd podczas duplikowania '{original_name}':\n{e}")

                else: # <<< Correct ELSE alignment
                    print(f"Error: Could not find parent for '{original_name}'.");
                    QMessageBox.critical(self, "Błąd Wew.", f"Nie można znaleźć rodzica dla '{original_name}'.")

            elif ok and not new_name.strip(): # <<< Correct ELIF alignment
                QMessageBox.warning(self, "Error", "Nazwa pusta.")
            # else: # Case where ok is False (dialog cancelled) - do nothing
            #    pass
        
    # --- Helpers ---
    def get_parent_element(self, child_element, file_path): # ... (same as before) ...
        if file_path not in self.loaded_files: return None
        root = self.loaded_files[file_path]['root']
        for parent in root.iter():
            try:
                if child_element in list(parent): return parent
            except TypeError: pass # Element is not iterable (like a comment)
        print(f"Warning: Could not find parent for {child_element.tag} ({child_element.attrib.get('name', 'N/A')})"); return None

    # Override closeEvent
    def closeEvent(self, event): # ... (same as before) ...
        if self.modified_files:
            reply = QMessageBox.question(self, 'Niezapisane Zmiany', "Masz niezapisane zmiany. Zapisać przed wyjściem?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save: self.save_all_files();
            if self.modified_files and reply != QMessageBox.StandardButton.Discard: event.ignore() # Prevent close if save failed or cancelled
            else: event.accept()
        else: event.accept()

    # --- List Filtering ---
    def filter_list(self, text, list_widget): # ... (same as before) ...
        for i in range(list_widget.count()): item = list_widget.item(i); item.setHidden(text.lower() not in item.text().lower())
    def filter_abilities(self, text): self.filter_list(text, self.ability_list)
    def filter_items(self, text): self.filter_list(text, self.item_list)


if __name__ == "__main__":
    if hasattr(Qt, 'AA_EnableHighDpiScaling'): QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'): QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # Apply basic Fusion dark palette
    app.setStyle("Fusion")
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35)) # Darker base for inputs/lists
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.black)
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218)) # Highlight color
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    # Disabled states
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))

    app.setPalette(dark_palette)
    # Optional: Force specific style hints if needed
    # app.styleHints().setColorScheme(Qt.ColorScheme.Dark)

    editor = WitcherXMLEditor()
    editor.show()
    sys.exit(app.exec())