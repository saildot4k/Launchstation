"""Read component sources for the few remaining structural contract checks.
Behavioral tests should compile the real modules against platform adapters.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPANIONS = {
    "src/filer_actions.c": ["src/filer_tree.c"],
    "src/filer_browser.c": ["src/filer_menu_rules.c"],
    "src/filer_saves.c": ["src/filer_save_progress.c", "src/filer_save_io.c", "src/filer_save_cards.c", "src/filer_save_export.c"],
    "src/dash_settings.c": ["src/dash_settings_clock.c", "src/dash_settings_theme.c"],
}

def component_source(path):
    return "\n".join((ROOT / name).read_text() for name in [path, *COMPANIONS.get(path, [])])
