#!/usr/bin/env python3
"""
XONOTIC MAPPING HELPER
======================

A small, dependency-free terminal tool for Xonotic mappers. It takes care of
the boring parts of a map project:

  1) Export Assets    - scan your .map file (brush faces, patches and entity
                        keys like 'model' or 'noise') and your own shader
                        scripts, then make sure the project has everything the
                        map uses - textures, shader scripts, sounds, models
                        (with skins/materials and their textures): already in
                        the project -> kept; in the wrong place -> moved (after
                        confirmation); missing -> copied from the search paths
                        (PK3s first, then loose files).
  2) Rename Map       - rename the map completely: map files, lightmap folder,
                        the title in the .mapinfo and the project folder, with
                        a preview + confirmation. Prefixes and suffixes are not
                        part of the map name, they only exist for the .pk3.
  3) Pack it          - build a ready-to-distribute .pk3 containing only the
                        files a map needs (the .map source can be included so
                        other people can open the map in NetRadiant). The .pk3
                        name can get a revision number; the map files inside
                        keep their names.

START MENU
----------
  When the tool starts you can either choose an existing map folder or create a
  new one. A new map folder is created with the usual layout of a Xonotic map
  package (maps/, textures/, scripts/, sound/, models/, env/, gfx/).

REQUIREMENTS
------------
  * Python 3.8 or newer. No third-party packages are needed.

PLACEMENT & EXECUTION
---------------------
  1. Put this script in your workspace directory, next to your map project
     folders, e.g.:

         workspace/
         |-- mapping_helper.py
         |-- MyMap/
         |   |-- maps/            <- .map / .bsp / .mapinfo / lightmaps live here
         |   |-- textures/
         |   |-- scripts/         <- your custom .shader files (optional)
         |   `-- ...
         `-- AnotherMap/

  2. Open a terminal in that folder and run:

         python3 mapping_helper.py

CONFIGURATION FILE
------------------
  Settings are stored in 'mapping_helper_config.json' next to the script and can
  be changed from the in-app settings menu (press 's'):
    * PK3 export path       - where finished .pk3 files are written
    * PK3 filename prefix   - e.g. 'duke_' -> duke_mymap.pk3
    * Revision format       - the suffix word before the number, e.g. 'r', 'v' or
                              'alpha' -> mymap_r3 / mymap_v3 / mymap_alpha3.
                              The number is asked when packing.
    * Search paths          - folders searched for assets (default ~/.xonotic):
                              all .pk3 files below them first, then loose files
    * Include .map source   - ship the editable .map inside the .pk3 (default: yes)
    * Projects folder       - where map folders are listed and created
                              (default: the folder this script lives in)

CODE LAYOUT
-----------
  The file is one script on purpose (copy it anywhere and run it). Inside, it
  is grouped into these sections, in this order. Every section starts with a
  banner comment, so you can search for its name:

     1. CONSTANTS                  paths, file formats, entity keys, filters
     2. CONSOLE HELPERS            ask / confirm / cancel words
     3. CONFIGURATION              settings file, search paths, projects folder
     4. ASSET SOURCES              where assets can come from (PK3s, folders)
     5. MAP FILE PARSING           what a .map file uses
     6. SHADER SCRIPTS             parsing .shader files, shaders inside PK3s
     7. MODELS                     what models, skins and materials refer to
     8. MAPINFO FILES              reading and updating the .mapinfo
     9. SHARED MAP HELPERS         picking the .map, folder-name rules
    10. OPTION 1: EXPORT ASSETS    the "make the project complete" feature
    11. OPTION 2: RENAME MAP       rename map files, title and project folder
    12. OPTION 3: PACK MAP         revision suffix and building the .pk3
    13. SETTINGS MENU              the settings screens
    14. HELP SCREEN                the help text
    15. PROJECT MENUS & MAIN LOOP  start menu, project menu, entry point
"""

from __future__ import annotations

import bisect
import json
import os
import posixpath
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

# Enable arrow keys, cursor movement and input history for input() on
# Linux/macOS. The 'readline' module is not available on Windows by default,
# where the console handles this natively, so a failed import is fine.
try:
    import readline  # noqa: F401  (imported for its side effect only)
except ImportError:
    pass


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

# The workspace directory is simply the folder this script lives in.
# All map project folders are expected to sit directly inside it.
BASE_MAPS_DIR = Path(__file__).resolve().parent

# Persistent settings live right next to the script.
CONFIG_FILE = BASE_MAPS_DIR / "mapping_helper_config.json"

# Default values for every setting. Missing keys in an old config file are
# filled from here, so adding new settings never breaks existing configs.
DEFAULT_CONFIG = {
    "custom_export_dir": None,    # None = write the .pk3 into the map folder
    "pk3_prefix": "",             # text put in front of the .pk3 file name
    "rev_prefix": "",             # text put between '_' and the revision number
    "xonotic_dirs": None,         # list of folders searched for assets; None = ~/.xonotic
    "include_map_source": True,   # ship maps/*.map inside the .pk3
    "projects_dir": None,         # None = the folder this script lives in
}

# Where Xonotic keeps the user's data on Linux. This is the only search path set
# by default; more can be added in the settings (e.g. an external asset library).
DEFAULT_XONOTIC_DIR = Path.home() / ".xonotic"

# Image formats the engine can load for textures.
IMAGE_EXTENSIONS = [".png", ".tga", ".jpg", ".dds"]

# Companion images that belong to a texture (glow, normal map, gloss, ...).
# The empty string is the plain diffuse texture itself.
MAP_SUFFIXES = [
    "", "_alpha", "_gloss", "_glow", "_glow_alpha",
    "_norm", "_norm_alpha", "_pants", "_shirt",
]

# Audio and 3D model formats the engine can load. A map may list a sound without
# its extension; the engine then tries these in order.
SOUND_EXTENSIONS = [".wav", ".ogg", ".flac"]

MODEL_EXTENSIONS = [".md3", ".iqm", ".obj", ".dpm", ".zym", ".psk", ".md2", ".mdl"]

# Binary model formats that keep their texture names as plain text inside.
BINARY_MODEL_EXTENSIONS = {".md3", ".iqm", ".dpm", ".zym", ".psk", ".md2", ".mdl"}

THUMBNAIL_EXTENSIONS = [".jpg", ".png", ".tga"]

# Lines of a .mtl material file that name a texture (map_Kd, bump, disp, ...).
MTL_TEXTURE_KEYS = ("map_", "bump", "disp", "decal", "refl")

# Entity keys in the .map that point to assets. Other keys are picked up too if
# their value looks like a path to a known file type (e.g. 'gfx/foo.tga').
SOUND_KEYS = {"noise", "noise1", "noise2", "sound"}

MODEL_KEYS = {"model", "model2"}

SKY_KEYS = {"skybox", "skyname", "sky"}

# Folders a path inside a model's skin/material file is relative to the game
# root; any other path is relative to the folder of that file.
ROOT_FOLDERS = ("textures/", "models/", "gfx/", "env/", "sound/")

# The six faces of a skybox, used for 'skyparms' lines in shader scripts.
SKY_FACE_SUFFIXES = ["_rt", "_lf", "_ft", "_bk", "_up", "_dn"]

# Editor-only "tool" textures. They only exist for the compiler/editor, so they
# never need to be shipped with a map.
TOOL_TEXTURES = {
    "common/caulk", "common/nodraw", "common/clip", "common/fullclip",
    "common/weapclip", "common/botclip", "common/trigger", "common/hint",
    "common/hintskip", "common/skip", "common/origin", "common/areaportal",
    "common/clusterportal", "common/donotenter", "common/nodrop",
    "common/noimpact", "common/nolightmap", "common/nonsolid",
    "common/structural",
}

# Brush faces come in two layouts depending on the map format NetRadiant saves:
#
#   classic:          ( x y z ) ( x y z ) ( x y z ) texture [ ...offsets... ]
#   brush primitives: ( x y z ) ( x y z ) ( x y z ) ( ( a b c ) ( d e f ) ) texture 0 0 0
#                     (the files that start each brush with a 'brushDef' line)
#
# The regex skips the three coordinate groups, then the OPTIONAL texture matrix
# of the brush-primitive layout, and captures the texture name that follows.
FACE_RE = re.compile(
    r'^\s*\(\s*[^)]+\)\s*\(\s*[^)]+\)\s*\(\s*[^)]+\)\s*'   # 3 plane points
    r'(?:\(\s*\(\s*[^)]*\)\s*\(\s*[^)]*\)\s*\)\s*)?'         # optional texture matrix
    r'("[^"]+"|\S+)'                                              # texture name
)

ENTITY_PAIR_RE = re.compile(r'^\s*"([^"]+)"\s+"([^"]*)"\s*$')

PATH_TOKEN_RE = re.compile(rb"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+")

COMPANION_TAIL_RE = re.compile(r"^(_[a-z0-9]+)?(\.[a-z0-9]+)?\.(skin|framegroups|mtl)$")

# --- Packing rules ---------------------------------------------------------
# Folders that are never packed (checked against every folder in the path).
IGNORE_DIRS = {".git", ".github", ".idea", ".vscode", "__pycache__"}

# Individual file names that are never packed.
IGNORE_FILES = {
    ".DS_Store", "Thumbs.db", ".gitignore",
    "mapping_helper.py", "mapping_helper_config.json",
}

# File extensions that are never packed: compiler by-products, logs, editor
# backups and typical working files of image/3D tools that players don't need.
EXCLUDED_EXTENSIONS = {
    ".pk3", ".bak", ".prt", ".srf", ".log", ".lin", ".tmp",
    ".xcf", ".psd", ".blend", ".blend1", ".fcstd", ".fcstd1",
}

# Sub-folders created for a new map project. They mirror the layout of a
# Xonotic map package. Empty folders are harmless: the packer only stores files.
NEW_PROJECT_SUBDIRS = [
    "maps",       # .map / .bsp / .mapinfo / levelshot, lightmaps are created here
    "textures",   # your own textures (and exported support textures)
    "scripts",    # custom .shader files
    "sound",      # sounds and music (e.g. sound/cdtracks)
    "models",     # .md3 / .obj models used with misc_model
    "env",        # skybox images
    "gfx",        # misc graphics, e.g. a loading screen
]

# Single-letter menu commands (help, settings, cancel, quit, and the legacy 'x').
# They must never be accepted as a folder name or a revision tag, otherwise
# pressing 's' at a name prompt would create a folder called 's'.
MENU_COMMANDS = {"c", "h", "q", "s", "x"}

# Words that cancel the current prompt and go back one level.
CANCEL_WORDS = ("c", "x", "q")

# ASCII art banner for the title screen.
ASCII_BANNER = r"""
 __  __                   _               _   _      _
|  \/  | __ _ _ __  _ __ (_)_ __   __ _  | | | | ___| |_ __   ___ _ __
| |\/| |/ _` | '_ \| '_ \| | '_ \ / _` | | |_| |/ _ \ | '_ \ / _ \ '__|
| |  | | (_| | |_) | |_) | | | | | (_| | |  _  |  __/ | |_) |  __/ |
|_|  |_|\__,_| .__/| .__/|_|_| |_|\__, | |_| |_|\___|_| .__/ \___|_|
             |_|   |_|            |___/               |_|
"""

# ---------------------------------------------------------------------------
# CONSOLE HELPERS
# ---------------------------------------------------------------------------


def ask(prompt: str) -> str:
    """Read one line from the user. Ctrl+C / Ctrl+D quit the program cleanly."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye!")
        sys.exit(0)


def confirm(question: str) -> bool:
    """Ask a yes/no question. Anything except 'y' / 'yes' counts as 'no'."""
    return ask(f"{question} [y/N]: ").lower() in ("y", "yes")


def is_cancel(text: str) -> bool:
    """True if the user typed one of the cancel words ('c', 'x' or 'q')."""
    return text.lower() in CANCEL_WORDS

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------


def load_config() -> dict:
    """Load settings from the JSON file, filling in defaults for missing keys."""
    config = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                config.update(data)
        except (OSError, json.JSONDecodeError) as e:
            # A broken config must not stop the tool - warn and use defaults.
            print(f"[WARNING] Could not read config file ({e}). Using defaults.")
    return config


def save_config(config: dict) -> None:
    """Write the settings dictionary to the JSON file next to the script."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except OSError as e:
        print(f"[ERROR] Could not save configuration file: {e}")


def clean_rev_prefix(value: str) -> str:
    """Normalize the revision prefix: '_r', 'r' and ' r ' all become 'r'."""
    return (value or "").strip().lstrip("_")


def get_xonotic_dirs() -> list[Path]:
    """Return the folders that are searched for assets, in priority order.

    Configured list (settings), else the folder of older versions of this
    script, else the default ~/.xonotic.
    """
    config = load_config()
    dirs = config.get("xonotic_dirs")
    if not dirs:
        old = config.get("xonotic_data_dir")          # single folder of older versions
        dirs = [old] if old else [DEFAULT_XONOTIC_DIR]
    return [Path(str(d)).expanduser() for d in dirs]


def get_workspace_dir() -> Path:
    """Return the folder in which map project folders are listed and created.

    This is the 'Projects folder' setting. If it is not set, the folder the
    script lives in is used, because the tool is designed to sit next to your
    map projects.
    """
    configured = load_config().get("projects_dir")
    return Path(configured) if configured else BASE_MAPS_DIR


def get_status_note(project_dir: Path | None = None) -> str:
    """Build the three-line status footer shown above every menu."""
    config = load_config()
    export_dir = config.get("custom_export_dir")
    if export_dir:
        dir_str = str(export_dir)
    else:
        dir_str = str(project_dir) if project_dir else "[Map Folder (Default)]"

    prefix = config.get("pk3_prefix", "")
    rev = config.get("rev_prefix", "")
    prefix_str = f"'{prefix}'" if prefix else "None"
    rev_str = f"'{rev}'" if rev else "None"
    map_src = "yes" if config.get("include_map_source") else "no"

    return (
        "  Note: h=help, s=settings, c=cancel, q=quit\n"
        f"  Export Path: {dir_str}\n"
        f"  Prefix: {prefix_str} | Rev: {rev_str} | .map in pk3: {map_src}"
    )

# ---------------------------------------------------------------------------
# ASSET SOURCES  (where assets can come from)
# ---------------------------------------------------------------------------


def get_searchable_pk3_files() -> list[Path]:
    """Find every .pk3 below the search paths (subfolders included).

    That covers data/, downloaded server maps (data/dlcache) and your own
    packs. 'Support' PK3s (name contains 'mapping' or 'extra') come first so
    the original game assets keep priority; otherwise the order of the search
    paths counts, and inside one path the files are sorted by path.
    """
    found = []
    for root in get_xonotic_dirs():
        if not root.is_dir():
            continue
        in_root = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for name in sorted(filenames):
                if name.lower().endswith(".pk3"):
                    in_root.append(Path(dirpath) / name)
        found.extend(p for p in sorted(in_root, key=str) if p not in found)
    support = [p for p in found if "mapping" in p.name.lower() or "extra" in p.name.lower()]
    others = [p for p in found if p not in support]
    return support + others


def get_loose_asset_folders() -> list[Path]:
    """Folders whose loose files the game reads like the content of a PK3.

    For every search path that is its 'data' folder (as in ~/.xonotic/data/
    textures/custom/foo.png), or the path itself if it has none (an asset
    library with textures/, sound/, ... directly inside), plus every
    '*.pk3dir' folder, which is how mappers work on a pack before zipping it.
    These are only searched after all PK3s.
    """
    folders = []

    def add(folder):
        if folder not in folders:
            folders.append(folder)

    for root in get_xonotic_dirs():
        if not root.is_dir():
            continue
        if (root / "data").is_dir():
            add(root / "data")
        else:
            add(root)
        for dirpath, dirnames, _ in os.walk(root):
            dirnames.sort()
            for name in dirnames:
                if name.lower().endswith(".pk3dir"):
                    add(Path(dirpath) / name)
    return folders


def build_pk3_index(pk3_paths: list[Path]) -> dict:
    """Index all files of all given PK3s ONCE.

    Returns {lowercase_path_in_archive: (pk3_path, real_path_in_archive)}.
    The first archive containing a file wins. Indexing up front is much faster
    than re-reading every archive for every texture, and the lowercase keys
    make the lookup independent of the original capitalization.
    """
    index = {}
    for pk3_path in pk3_paths:
        try:
            with zipfile.ZipFile(pk3_path, "r") as pk3:
                for name in pk3.namelist():
                    if not name.endswith("/"):
                        index.setdefault(name.lower(), (pk3_path, name))
        except (zipfile.BadZipFile, OSError) as e:
            print(f"[WARNING] Skipping unreadable archive {pk3_path.name}: {e}")
    return index


def build_folder_index(folders: list[Path]) -> dict:
    """Index the loose files of folders, same format as build_pk3_index.

    Returns {lowercase_relative_path: (folder, real_relative_path)}. The first
    folder containing a file wins. .pk3 files themselves are skipped (they are
    searched as archives) and so are '*.pk3dir' folders inside a folder (they
    are searched as folders of their own).
    """
    index = {}
    for folder in folders:
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = sorted(d for d in dirnames if not d.lower().endswith(".pk3dir"))
            for name in sorted(filenames):
                if name.lower().endswith(".pk3"):
                    continue
                real = (Path(dirpath) / name).relative_to(folder).as_posix()
                index.setdefault(real.lower(), (folder, real))
    return index


def build_local_index(project_dir: Path) -> dict:
    """Index the files that already are in the project folder.

    Same format as build_pk3_index, with None instead of a PK3. Assets you made
    yourself exist only here; they must not be reported as 'not found'.
    """
    local = {}
    for dirpath, dirnames, filenames in os.walk(project_dir):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            real = (Path(dirpath) / name).relative_to(project_dir).as_posix()
            local.setdefault(real.lower(), (None, real))
    return local


def source_label(source: Path) -> str:
    """Short name of an asset source for messages: a .pk3 or a folder."""
    return f"{source.name} (folder)" if source.is_dir() else source.name


def find_in_index(index: dict, value: str, extensions: list,
                  prefixes: tuple = ("",)) -> str | None:
    """Look a path up in the PK3 index and return the matching index key.

    If 'value' has one of the 'extensions' it is tried as it is first, then
    with the other extensions (a map may say .wav while the file is an .ogg).
    Without such an extension, every extension is appended in turn. Each
    prefix (e.g. 'sound/') is tried in order. Returns None if nothing matches.
    """
    base, ext = posixpath.splitext(value)
    if ext in extensions:
        names = [value] + [base + e for e in extensions if e != ext]
    else:
        names = [value + e for e in extensions]
    for prefix in prefixes:
        for name in names:
            if prefix + name in index:
                return prefix + name
    return None


def similar_files(names: list, index: dict, limit: int = 3) -> dict:
    """For names that were not found: files with the same name at another path.

    A typical cause of 'not found' is a different folder or extension, so this
    shows where a file with that name does exist.
    """
    def stem_of(path):
        return posixpath.splitext(posixpath.basename(path))[0]

    wanted = {}
    for name in names:
        wanted.setdefault(stem_of(name), []).append(name)
    hints = {name: [] for name in names}
    for key, (pk3_path, real_name) in index.items():
        for name in wanted.get(stem_of(key), []):
            if len(hints[name]) < limit:
                source = source_label(pk3_path) if pk3_path else "your project"
                hints[name].append(f"{real_name}  ({source})")
    return hints


class AssetCopier:
    """Copies files out of PK3s into the project folder - safely.

    * never writes outside the project folder (even for archives with '../')
    * never overwrites a file that already exists
    * keeps each PK3 open while copying; call close() at the end
    """

    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.root = project_dir.resolve()
        self.archives = {}
        self.copied = 0
        self.skipped = 0
        self.local_only = set()      # files that exist only in the project

    def copy(self, pk3_path, real_name, announce=True, count=True):
        """Copy one file. Returns 'copied', 'exists', 'local' or 'blocked'.

        'local' means the file is not in any PK3, it only exists in the
        project folder (pk3_path is None) - nothing to copy.
        """
        if pk3_path is None:
            self.local_only.add(real_name)
            return "local"
        target = self.project_dir / real_name
        if self.root not in target.resolve().parents:
            return "blocked"
        if target.exists():
            if count:
                self.skipped += 1
            return "exists"
        target.parent.mkdir(parents=True, exist_ok=True)
        if pk3_path.is_dir():
            shutil.copyfile(pk3_path / real_name, target)      # loose file
        else:
            if pk3_path not in self.archives:
                self.archives[pk3_path] = zipfile.ZipFile(pk3_path, "r")
            with self.archives[pk3_path].open(real_name) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
        if count:
            self.copied += 1
        if announce:
            print(f"  [+] Copied ({source_label(pk3_path)}): {real_name}")
        return "copied"

    def close(self):
        for archive in self.archives.values():
            archive.close()


def sound_slot(value: str) -> str:
    """Where a sound belongs in the project: 'sound/<name>' without extension.

    A map says 'misc/hit.wav' (relative to sound/) or 'sound/misc/hit.wav'.
    """
    base, ext = posixpath.splitext(value)
    if ext not in SOUND_EXTENSIONS:
        base = value
    return base if base.startswith("sound/") else "sound/" + base


def has_asset(index: dict, base: str, extensions: list) -> bool:
    """True if 'base' + one of the extensions is in the index (lowercase keys)."""
    return any(f"{base}{ext}" in index for ext in extensions)

# ---------------------------------------------------------------------------
# MAP FILE PARSING  (what a .map uses)
# ---------------------------------------------------------------------------


def strip_image_extension(name: str) -> str:
    """Remove a trailing .tga/.png/.jpg/.dds from a texture reference."""
    for ext in IMAGE_EXTENSIONS:
        if name.endswith(ext):
            return name[:-len(ext)]
    return name


def normalize_brush_texture(name: str) -> str:
    """Turn a texture name from a .map file into 'textures/<name>' (lowercase).

    Radiant stores names without the implicit 'textures/' folder, so we add it
    unless it is already there. File extensions are removed.
    """
    name = strip_image_extension(name.lower().replace("\\", "/"))
    return name if name.startswith("textures/") else f"textures/{name}"


def extract_used_textures(map_file_path: Path) -> set:
    """Parse a .map file and return the set of used texture names.

    Handles two kinds of surfaces:
      * normal brush faces  (matched line by line with FACE_RE)
      * patches (curves)    - 'patchDef2' / 'patchDef3' is followed by '{' and
                              then a line that contains only the texture name
    Tool textures (caulk, clip, ...) and 'noshader' are skipped.
    """
    used = set()
    expecting_patch_texture = False

    with open(map_file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()

            # --- Patches: the texture is the first real line after 'patchDef'.
            if expecting_patch_texture:
                if stripped in ("", "{"):
                    continue                    # still inside the patch header
                expecting_patch_texture = False
                used.add(stripped.lower())
                continue
            if stripped.lower().startswith(("patchdef2", "patchdef3")):
                expecting_patch_texture = True
                continue

            # --- Brush faces.
            match = FACE_RE.match(line)
            if match:
                used.add(match.group(1).strip('"').lower())

    # Filter out editor/tool shaders and invalid captures, then normalize.
    result = set()
    for raw in used:
        clean = strip_image_extension(raw.replace("\\", "/"))
        if not clean or clean.startswith("(") or clean.startswith("noshader"):
            continue
        if clean in TOOL_TEXTURES:
            continue
        result.add(normalize_brush_texture(clean))
    return result


def read_entity_pairs(map_file_path: Path) -> list:
    """Return all '"key" "value"' pairs of the entities in a .map (key lowercase)."""
    pairs = []
    with open(map_file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            match = ENTITY_PAIR_RE.match(line)
            if match:
                pairs.append((match.group(1).lower(), match.group(2)))
    return pairs


def fix_absolute_path(value: str) -> tuple:
    """Cut an absolute path down to the part relative to the game root.

    NetRadiant sometimes stores '/home/me/mymap/sound/x.ogg' instead of
    'sound/x.ogg' when a file is picked in a file dialog. Such a path only
    works on the computer it was made on. Returns (path, was_absolute).
    """
    if not (value.startswith("/") or re.match(r"^[a-z]:/", value)):
        return value, False
    best = max((value.rfind("/" + folder) for folder in ROOT_FOLDERS), default=-1)
    return (value[best + 1:] if best >= 0 else value.lstrip("/")), True


def classify_entity_value(key: str, value: str) -> str | None:
    """Decide what an entity value points to: 'sound', 'model', 'texture' or None.

    Known keys ('noise', 'model', 'skybox', ...) decide on their own. For all
    other keys a value only counts if it looks like a path ('dir/file') with a
    known extension.
    """
    if key in SOUND_KEYS:
        return "sound"
    if key in MODEL_KEYS:
        return "model"
    if key in SKY_KEYS:
        return "texture"
    if " " in value or "/" not in value:
        return None
    ext = posixpath.splitext(value)[1]
    if ext in SOUND_EXTENSIONS:
        return "sound"
    if ext in MODEL_EXTENSIONS:
        return "model"
    if ext in IMAGE_EXTENSIONS:
        return "texture"
    return None


def collect_entity_assets(pairs: list) -> tuple:
    """Sort the entity values of a map into sounds, models and texture names.

    Inline brush models ('*3') are ignored. Absolute paths are cut down to
    their game-relative part and reported.
    Returns (sounds, models, textures, absolute): three sets of lowercase paths
    and a list of (key, original value, used value) for absolute paths.
    """
    sounds, models, textures, absolute = set(), set(), set(), []
    for key, raw in pairs:
        original = raw.strip()
        value, was_absolute = fix_absolute_path(original.replace("\\", "/").lower())
        value = value.lstrip("/")
        if not value or value.startswith("*"):
            continue
        kind = classify_entity_value(key, value)
        if kind == "sound":
            sounds.add(value)
        elif kind == "model":
            models.add(value)
        elif kind == "texture":
            textures.add(strip_image_extension(value))
        if kind and was_absolute and (key, original, value) not in absolute:
            absolute.append((key, original, value))
    return sounds, models, textures, absolute

# ---------------------------------------------------------------------------
# SHADER SCRIPTS
# ---------------------------------------------------------------------------


def images_from_shader_line(tokens: list) -> set:
    """Images named by one line inside a shader's braces.

    Understands 'map' / 'clampmap', 'animmap <fps> <image> ...' and
    'skyparms <base> ...' (a skybox expands to its six faces). Anything else,
    like blendfunc or surfaceparm, names no image.
    """
    key = tokens[0].lower()
    if key in ("map", "clampmap") and len(tokens) > 1:
        if tokens[1].startswith("$"):                  # $lightmap etc. are no files
            return set()
        return {strip_image_extension(tokens[1].lower())}
    if key == "animmap":
        return {strip_image_extension(token.lower()) for token in tokens[2:]}
    if key == "skyparms" and len(tokens) > 1 and tokens[1] != "-":
        base = tokens[1].lower()
        return {base + suffix for suffix in SKY_FACE_SUFFIXES}
    return set()


def parse_shader_text(text: str) -> dict:
    """Parse the text of a .shader script into {shader_name: {image, ...}}.

    Shader names are the names declared at brace depth 0, e.g.
    'textures/mymap/lamp'. The images of a shader are the paths used inside
    its braces (see images_from_shader_line). Image references that appear
    before any shader name are stored under the key ''.
    """
    blocks = {}
    current = None
    depth = 0

    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()          # drop comments
        if not line:
            continue
        tokens = line.split()

        if depth == 0:
            # Outside any braces a line is the name of a new shader.
            if tokens[0] not in ("{", "}"):
                current = strip_image_extension(tokens[0].lower().replace("\\", "/"))
                blocks.setdefault(current, set())
        else:
            images = blocks.setdefault(current if current is not None else "", set())
            images |= images_from_shader_line(tokens)

        # Track brace depth AFTER handling the line itself.
        depth = max(0, depth + line.count("{") - line.count("}"))

    return blocks


def read_shader_blocks(shader_path: Path) -> dict:
    """Read a .shader file from disk and parse it (see parse_shader_text)."""
    with open(shader_path, "r", encoding="utf-8", errors="ignore") as f:
        return parse_shader_text(f.read())


def find_pk3_shaders(index: dict, wanted: set) -> dict:
    """Find shaders inside the PK3s that define the wanted texture names.

    Many textures (sprites with alpha, animated or sky textures, ...) only work
    through a shader in 'scripts/*.shader'. This searches those scripts in the
    indexed PK3s (same priority as the images: the first archive/folder/file that
    defines a name wins) and returns
        {texture_name: (pk3_path, shader_path_in_archive, images_of_that_shader)}
    Only scripts that mention at least one wanted name are parsed.
    """
    found = {}
    if not wanted:
        return found
    archives = {}
    try:
        for key, (pk3_path, real_name) in index.items():
            if not (key.startswith("scripts/") and key.endswith(".shader")):
                continue
            open_wanted = wanted - set(found)
            if not open_wanted:
                break
            try:
                if pk3_path.is_dir():                      # loose shader script
                    text = (pk3_path / real_name).read_text(encoding="utf-8", errors="ignore")
                else:
                    if pk3_path not in archives:
                        archives[pk3_path] = zipfile.ZipFile(pk3_path, "r")
                    text = archives[pk3_path].read(real_name).decode("utf-8", errors="ignore")
            except (KeyError, OSError, zipfile.BadZipFile):
                continue
            lowered = text.lower()
            if not any(name in lowered for name in open_wanted):
                continue
            for name, images in parse_shader_text(text).items():
                if name in open_wanted:
                    found[name] = (pk3_path, real_name, images)
    finally:
        for archive in archives.values():
            archive.close()
    return found

# ---------------------------------------------------------------------------
# MODELS
# ---------------------------------------------------------------------------


def companion_keys(sorted_keys: list, model_key: str) -> list:
    """Files that belong to a model by name: skins, framegroups, materials.

    For 'models/a/b.md3' that is e.g. 'b_default.skin', 'b_0.skin',
    'b.md3.framegroups', 'b.framegroups' or 'b.mtl'.
    """
    stem = posixpath.splitext(model_key)[0]
    result = []
    pos = bisect.bisect_left(sorted_keys, stem)
    while pos < len(sorted_keys) and sorted_keys[pos].startswith(stem):
        key = sorted_keys[pos]
        if key != model_key and COMPANION_TAIL_RE.match(key[len(stem):]):
            result.append(key)
        pos += 1
    return result


def model_relative_path(name: str, model_dir: str) -> str:
    """Resolve a path found inside a model file.

    Paths that start with a game folder (textures/, models/, ...) are relative
    to the game root; anything else is relative to the folder of the model.
    """
    name = name.replace("\\", "/").lower().lstrip("/")
    return name if name.startswith(ROOT_FOLDERS) else posixpath.join(model_dir, name)


def scan_binary_model(data: bytes) -> set:
    """Texture names of a binary model (.md3, .iqm, ...).

    They are stored as plain text strings inside the file, so every
    'folder/name' looking string counts, except references to other models
    and sounds.
    """
    textures = set()
    for token in PATH_TOKEN_RE.findall(data):
        name = token.decode("latin-1").lower()
        if posixpath.splitext(name)[1] in MODEL_EXTENSIONS + SOUND_EXTENSIONS:
            continue
        textures.add(strip_image_extension(name))
    return textures


def scan_skin_text(text: str) -> set:
    """Texture names of a .skin file: one 'meshname,texture/path' per line."""
    textures = set()
    for line in text.splitlines():
        if "," not in line:
            continue
        name = line.split(",", 1)[1].strip().replace("\\", "/").lower()
        if name:
            textures.add(strip_image_extension(name))
    return textures


def scan_mtl_text(text: str, model_dir: str) -> set:
    """Texture names of a .mtl material file (map_Kd, bump, ... lines)."""
    textures = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].lower().startswith(MTL_TEXTURE_KEYS):
            textures.add(strip_image_extension(model_relative_path(parts[-1], model_dir)))
    return textures


def scan_obj_text(text: str, model_dir: str, index: dict) -> list:
    """The .mtl files an .obj names with 'mtllib' (only those that exist in the index)."""
    materials = []
    for line in text.splitlines():
        if not line.lower().startswith("mtllib"):
            continue
        name = line[6:].strip()
        if name:
            candidate = model_relative_path(name, model_dir)
            if candidate in index:
                materials.append(candidate)
    return materials


def scan_model_file(path: Path, key: str, index: dict) -> tuple:
    """Find what a model-related file refers to.

    Returns (texture_names, extra_files): texture names are shader/image
    names without extension, extra_files are further files to copy (the
    .mtl of an .obj).
    """
    ext = posixpath.splitext(key)[1]
    model_dir = posixpath.dirname(key)
    try:
        data = path.read_bytes()
    except OSError:
        return set(), []

    if ext in BINARY_MODEL_EXTENSIONS:
        return scan_binary_model(data), []

    text = data.decode("utf-8", errors="ignore")
    if ext == ".skin":
        return scan_skin_text(text), []
    if ext == ".mtl":
        return scan_mtl_text(text, model_dir), []
    if ext == ".obj":
        return set(), scan_obj_text(text, model_dir, index)
    return set(), []

# ---------------------------------------------------------------------------
# MAPINFO FILES
# ---------------------------------------------------------------------------


def read_mapinfo_value(mapinfo_path: Path, key: str) -> str | None:
    """Return the value of the first 'key value' line of a .mapinfo, or None.

    Comments after '//' are removed ('cdtrack song.ogg // Artist - Title').
    """
    with open(mapinfo_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.split("//", 1)[0].strip().split(None, 1)
            if len(parts) == 2 and parts[0].lower() == key:
                return parts[1].strip()
    return None


def update_mapinfo_title(mapinfo_path: Path, new_title: str) -> None:
    """Set the 'title' line of a .mapinfo to 'new_title' (added if missing).

    Only the first title line is touched. Encoding errors and line endings are
    preserved byte-for-byte ('surrogateescape' + newline='').
    """
    with open(mapinfo_path, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        lines = f.readlines()

    # Matches e.g. 'title Space Hangar' -> groups: 'title ', value, trailing
    title_re = re.compile(r"^(\s*title\s+)(.*?)(\s*)$", re.IGNORECASE)
    found = False
    for i, line in enumerate(lines):
        match = title_re.match(line)
        if match and not found:
            found = True
            lines[i] = f"{match.group(1)}{new_title}{match.group(3)}"

    if not found:
        # No title yet: add one, making sure the previous line is terminated.
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += "\n"
        lines.append(f"title {new_title}\n")

    with open(mapinfo_path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.writelines(lines)

# ---------------------------------------------------------------------------
# SHARED MAP HELPERS
# ---------------------------------------------------------------------------


def find_map_sources(maps_dir: Path) -> list[Path]:
    """Return all real .map source files in maps/ (newest first).

    Editor autosaves such as 'name.autosave.map' are ignored.
    """
    candidates = [
        p for p in maps_dir.glob("*.map")
        if p.is_file() and ".autosave" not in p.name.lower()
    ]
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)


def pick_map_file(maps_dir: Path) -> Path | None:
    """Let the user choose a .map file if there is more than one.

    Returns the chosen Path, or None if there is none / the user cancelled.
    """
    candidates = find_map_sources(maps_dir)
    if not candidates:
        print(f"[ERROR] No .map file found in '{maps_dir}'!")
        return None
    if len(candidates) == 1:
        return candidates[0]

    print("\nMultiple .map files found (newest first):")
    for i, path in enumerate(candidates, start=1):
        print(f"  {i}) {path.name}")
    choice = ask("> Select file: ").lower()
    if is_cancel(choice):
        print("[INFO] Cancelled.")
        return None
    if choice == "":
        return candidates[0]
    if choice.isdigit() and 1 <= int(choice) <= len(candidates):
        return candidates[int(choice) - 1]
    print("[ERROR] Invalid selection.")
    return None


def validate_project_name(name: str) -> str | None:
    """Return an error message if 'name' is not a usable folder name, else None.

    Only letters, digits, '_' and '-' are allowed. Map names end up in file
    names, console commands and map lists, where spaces and special characters
    cause trouble.
    """
    if name.lower() in MENU_COMMANDS:
        return f"'{name}' is reserved for menu commands (h, s, c, q, x)."
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        return "Use only letters, digits, '_' and '-' (no spaces or other characters)."
    if name in IGNORE_DIRS:
        return f"'{name}' is a reserved name."
    return None

# ---------------------------------------------------------------------------
# OPTION 1: EXPORT ASSETS
# ---------------------------------------------------------------------------


def copy_sounds(sounds: set, local_index: dict, search_index: dict,
                copier: AssetCopier) -> tuple:
    """Copy the sounds the project does not have yet.

    Returns (sounds that were found nowhere, number already in the project).
    """
    missing, present = [], 0
    for value in sorted(sounds):
        if has_asset(local_index, sound_slot(value), SOUND_EXTENSIONS):
            present += 1
            continue
        key = find_in_index(search_index, value, SOUND_EXTENSIONS, prefixes=("sound/", ""))
        if key is None:
            missing.append(value)
            continue
        copier.copy(*search_index[key])
    return missing, present


def copy_models(models: set, local_index: dict, search_index: dict,
                copier: AssetCopier) -> tuple:
    """Copy the models the project does not have yet, with their companion files,
    and find the textures all models use (a model already in the project is
    scanned too, but never replaced).

    Returns (missing_models, texture_names, number_already_in_project).
    """
    missing, textures, present = [], set(), 0
    combined = dict(search_index)
    combined.update(local_index)                 # the project's own files win
    sorted_keys = sorted(combined)
    seen = set()
    for value in sorted(models):
        key = find_in_index(local_index, value, MODEL_EXTENSIONS)
        is_local = key is not None
        if not is_local:
            key = find_in_index(search_index, value, MODEL_EXTENSIONS)
        if key is None:
            missing.append(value)
            continue
        present += is_local
        # Companions come from the same side as the model itself.
        queue = [key] + [k for k in companion_keys(sorted_keys, key)
                         if (combined[k][0] is None) == is_local]
        position = 0
        while position < len(queue):         # the queue can grow (.obj -> .mtl)
            item = queue[position]
            position += 1
            if item in seen:
                continue
            seen.add(item)
            pk3_path, real_name = combined[item]
            if copier.copy(pk3_path, real_name) == "blocked":
                continue
            found_textures, extra = scan_model_file(copier.project_dir / real_name, item, combined)
            textures |= found_textures
            queue.extend(extra)
    return missing, textures, present


def find_misplaced(missing_slots: dict, all_slots: set,
                   local_index: dict) -> tuple:
    """Find project files that sit in the wrong place.

    missing_slots: {expected_base: extensions} for assets that are not where
    the map expects them. A file in the project counts as the misplaced asset
    if its name (without extension) is the same and it is the only such file.
    Files that sit correctly for another asset, and the maps/ folder
    (lightmaps), are never touched.
    Returns ({expected_base: real_path}, {expected_base: [real_paths]}) - the
    first for unambiguous matches, the second for names with several matches.
    """
    by_stem = {}
    for base in missing_slots:
        by_stem.setdefault(posixpath.basename(base), []).append(base)
    candidates = {base: [] for base in missing_slots}
    for key, (_, real) in local_index.items():
        if key.startswith("maps/"):
            continue
        stem, ext = posixpath.splitext(posixpath.basename(key))
        if posixpath.splitext(key)[0] in all_slots:
            continue                                  # correct place for another asset
        for base in by_stem.get(stem, []):
            if ext in missing_slots[base]:
                candidates[base].append(real)
    unique = {b: c[0] for b, c in candidates.items() if len(c) == 1}
    ambiguous = {b: c for b, c in candidates.items() if len(c) > 1}
    return unique, ambiguous


def plan_moves(found: dict, image_slots: dict, local_index: dict) -> list:
    """Turn the misplaced files into a list of (source, destination) moves.

    Companion maps (_norm, _gloss, ...) next to a misplaced texture move with it.
    """
    moves = []
    for base, real in sorted(found.items()):
        folder, filename = posixpath.split(real)
        stem, ext = posixpath.splitext(filename)
        ext = ext.lower()
        moves.append((real, base + ext))
        if base not in image_slots:
            continue
        for suffix in MAP_SUFFIXES:
            if not suffix:
                continue
            for image_ext in IMAGE_EXTENSIONS:
                key = posixpath.join(folder, stem + suffix + image_ext).lower()
                destination = base + suffix + image_ext
                if key in local_index and destination not in local_index:
                    moves.append((local_index[key][1], destination))
    return moves


def apply_moves(moves: list, project_dir: Path) -> int:
    """Move the files. Never overwrites, never leaves the project folder."""
    root = project_dir.resolve()
    done = 0
    for source_rel, target_rel in moves:
        source = project_dir / source_rel
        target = project_dir / target_rel
        if root not in target.resolve().parents or not source.exists() or target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        print(f"  [FIX] Moved: {source_rel}  ->  {target_rel}")
        done += 1
    return done


def check_map_extras(project_dir: Path, map_base: str, local_index: dict,
                     search_index: dict | None = None) -> None:
    """Report things around the map that are easy to forget.

    * the thumbnail shown in the map list: maps/<name>.jpg (or .png / .tga)
    * the .mapinfo, and the music named by its 'cdtrack' line
      (sound/cdtracks/<track>): is it in the project?

    Only reports, never changes anything. With a search_index (Export Assets)
    a music file that is not in the project is also looked up in the search
    paths; without it (packing) only the project is checked.
    """
    base = map_base.lower()
    if not has_asset(local_index, f"maps/{base}", THUMBNAIL_EXTENSIONS):
        print(f"[WARNING] No thumbnail found: maps/{map_base}.jpg (also .png or .tga).")
        print("          It is the picture shown in the map list of the game.")

    mapinfo_key = f"maps/{base}.mapinfo"
    if mapinfo_key not in local_index:
        print(f"[WARNING] No maps/{map_base}.mapinfo found "
              f"(title, description and game types come from it).")
        return
    track = read_mapinfo_value(project_dir / local_index[mapinfo_key][1], "cdtrack")
    if not track or track.isdigit():              # no music line, or a CD track number
        return
    slot = sound_slot(f"cdtracks/{track.lower()}")
    expected = f"sound/cdtracks/{track}"
    if has_asset(local_index, slot, SOUND_EXTENSIONS):
        print(f"[INFO] Music from the .mapinfo (cdtrack): {expected} is in your project.")
        return
    if search_index is None:
        print(f"[WARNING] Music from the .mapinfo (cdtrack) is not in your project: {expected}")
        print("          Fine if it ships with the game, otherwise players hear no music.")
        return
    key = find_in_index(search_index, f"cdtracks/{track.lower()}", SOUND_EXTENSIONS,
                        prefixes=("sound/", ""))
    if key is not None:
        source, real = search_index[key]
        print(f"[INFO] Music from the .mapinfo (cdtrack) is not in your project, but exists in "
              f"the search paths ({source_label(source)}): {real}")
        print("       It is not copied - add it yourself if it is your own music.")
    else:
        print(f"[WARNING] Music from the .mapinfo (cdtrack) was not found in your project or the "
              f"search paths: {expected}")
        print("          Fine if it ships with the game, otherwise players hear no music.")


@dataclass
class MapNeeds:
    """Everything the .map file asks for, before anything is looked up."""
    brush_textures: set       # texture names used by brush faces and patches
    sounds: set               # sound paths from entity keys
    models: set               # model paths from entity keys
    entity_textures: set      # sky / image names from entity keys
    absolute: list            # (key, original value, used value) of absolute paths


def read_map_needs(map_file: Path) -> MapNeeds:
    """Parse the .map and report what it uses (plus absolute-path warnings)."""
    brush_textures = extract_used_textures(map_file)
    sounds, models, entity_textures, absolute = collect_entity_assets(read_entity_pairs(map_file))
    print(f"[SUCCESS] Found {len(brush_textures)} unique textures, {len(sounds)} sound(s) "
          f"and {len(models)} model(s) in the .map file.")
    for key, original, used in absolute:
        hint = used[len("sound/"):] if key in SOUND_KEYS and used.startswith("sound/") else used
        print(f'[WARNING] Absolute path in the map: "{key}" "{original}"')
        print(f'          That only works on your computer. '
              f'Change the value to "{hint}" in NetRadiant.')
    return MapNeeds(brush_textures, sounds, models, entity_textures, absolute)


def parse_project_shaders(project_dir: Path) -> dict:
    """Read the project's own shader scripts. Returns {shader name: {images}}."""
    own_shaders = {}
    scripts_dir = project_dir / "scripts"
    if not scripts_dir.is_dir():
        return own_shaders
    for shader_file in sorted(scripts_dir.glob("*.shader")):
        blocks = read_shader_blocks(shader_file)
        defined = {n for n in blocks if n}
        referenced = set().union(*blocks.values()) if blocks else set()
        for name in defined:
            own_shaders.setdefault(name, set()).update(blocks[name])
        print(f"[INFO] Parsed shader script: {shader_file.name} "
              f"({len(defined)} shaders, {len(referenced)} image references)")
    return own_shaders


def open_search_sources() -> dict | None:
    """Index everything the search paths offer: PK3s first, loose files as fallback.

    Returns the index {lowercase path: (source, real path)}, or None (after
    printing an error) if the search paths hold nothing to search.
    """
    search_dirs = get_xonotic_dirs()
    pk3_files = get_searchable_pk3_files()
    loose_folders = get_loose_asset_folders()
    if not pk3_files and not loose_folders:
        print(f"[ERROR] No PK3s or data folders found in {[str(d) for d in search_dirs]}!")
        print("        Set the correct search paths in the settings menu (press 's').")
        return None
    where = ", ".join(str(d) for d in search_dirs)
    if len(pk3_files) <= 10:
        print(f"[INFO] Scanning {len(pk3_files)} archive(s): {[p.name for p in pk3_files]}")
    else:
        print(f"[INFO] Scanning {len(pk3_files)} archives in {where} (this can take a moment)...")
    if loose_folders:
        print(f"[INFO] Then loose files in {len(loose_folders)} folder(s): "
              f"{[str(f) for f in loose_folders]}")
    search_index = build_pk3_index(pk3_files)
    for key, value in build_folder_index(loose_folders).items():
        search_index.setdefault(key, value)      # PK3s first, loose files only as fallback
    return search_index


def split_custom_shaders(texture_names: set, own_shaders: dict) -> tuple:
    """Separate the texture names that are your own shaders from the rest.

    Only the shaders the map really uses count, so unused shaders in a big
    script do not pull in extra images. Returns
    (images used by those shaders, texture names without an own shader).
    """
    custom = {t for t in texture_names if t in own_shaders}
    own_images = set()
    for name in custom:
        own_images |= own_shaders[name]
    if custom:
        print(f"[INFO] {len(custom)} texture name(s) are your own shaders "
              f"(images are taken from the shader files instead).")
    return own_images, texture_names - custom


def offer_corrections(project_dir: Path, image_slots: dict, sound_slots: dict,
                      local_index: dict) -> tuple:
    """Offer to move misplaced project files to the place the map expects them.

    Returns (number of moved files, the possibly refreshed local index).
    """
    all_slots = {**image_slots, **sound_slots}
    missing_slots = {b: e for b, e in all_slots.items() if not has_asset(local_index, b, e)}
    found, ambiguous = find_misplaced(missing_slots, set(all_slots), local_index)
    moves = plan_moves(found, image_slots, local_index)
    moved = 0
    if moves:
        print("\n[INFO] These assets are in your project, but not where the map expects them:")
        for source_rel, target_rel in moves:
            print(f"  {source_rel}  ->  {target_rel}")
        if confirm("\n> Move them to the expected place?"):
            moved = apply_moves(moves, project_dir)
            local_index = build_local_index(project_dir)
        else:
            print("[INFO] Left as they are. Missing assets are taken from the search paths.")
    for base, paths in sorted(ambiguous.items()):
        print(f"[INFO] More than one file could be '{base}', nothing moved: {', '.join(paths)}")
    return moved, local_index


def copy_pk3_shaders(shader_files: dict, copier: AssetCopier) -> int:
    """Copy the shader scripts that define map textures. Returns how many were copied."""
    copied = 0
    for (pk3_path, real_name), names in sorted(shader_files.items(), key=lambda kv: kv[0][1]):
        status = copier.copy(pk3_path, real_name, announce=False, count=False)
        if status == "exists":
            print(f"  [!] Shader script already exists, not overwritten: {real_name}")
            print(f"      It does not define: {', '.join(names)}")
        elif status == "copied":
            print(f"  [+] Copied shader ({source_label(pk3_path)}): {real_name}  "
                  f"(defines: {', '.join(names)})")
            copied += 1
    return copied


def copy_texture_images(needed: set, local_index: dict, search_index: dict,
                        copier: AssetCopier) -> tuple:
    """Copy the images of the needed textures that the project does not have yet.

    Returns (names that were found nowhere, number already in the project).
    """
    missing, present = [], 0
    for image_base in sorted(needed):
        if has_asset(local_index, image_base, IMAGE_EXTENSIONS):
            present += 1                             # e.g. a shader image already there
            continue
        found_any = False
        # Try the plain texture plus every companion map, in every format.
        for suffix in MAP_SUFFIXES:
            for ext in IMAGE_EXTENSIONS:
                hit = search_index.get(f"{image_base}{suffix}{ext}")
                if hit is None:
                    continue
                found_any = True
                copier.copy(*hit)
        if not found_any:
            missing.append(image_base)
    return missing, present


def print_not_found(groups: list, index: dict) -> None:
    """List what was found nowhere, with 'similar' files at other paths as a hint."""
    if not any(names for _, names in groups):
        return
    print("\n[INFO] Not found in your project or in the search paths:")
    for label, names in groups:
        if not names:
            continue
        hints = similar_files(names, index)
        print(f"  {label}:")
        for name in names:
            print(f"    [?] {name}")
            for hint in hints[name]:
                print(f"        similar: {hint}")
    print("      These are usually shipped with the base game (players already have")
    print("      them) or defined by a shader. 'similar' shows a file with the same")
    print("      name at another path, a common cause of 'not found'.")


def export_assets(project_dir: Path) -> None:
    """Make sure the project has everything the map uses.

    For every asset (texture, shader script, sound, model) the order is:
      1. It is in the project folder at the expected place: nothing to do.
      2. It is in the project folder at a wrong place: move it there (after
         you confirm).
      3. It is missing: take it from the search paths - first from the PK3s,
         then from loose files.
    Files go to the same folders they have inside the PKs, and existing files
    in the project are never overwritten.
    """
    maps_dir = project_dir / "maps"
    if not maps_dir.is_dir():
        print(f"[ERROR] Subfolder '{maps_dir}' does not exist!")
        return

    map_file = pick_map_file(maps_dir)
    if map_file is None:
        return
    print(f"\n[INFO] Analyzing map file: {map_file.name}...")

    needs = read_map_needs(map_file)                           # 1) what the map uses
    own_shaders = parse_project_shaders(project_dir)           # 2) your own shaders
    search_index = open_search_sources()                       # 3) where to take from
    if search_index is None:
        return
    local_index = build_local_index(project_dir)

    copier = AssetCopier(project_dir)
    shaders_copied = 0
    try:
        # 4) Models: the project first, then the search paths. Models can name
        #    textures themselves (inside the model, in .skin / .mtl files),
        #    which are handled like map textures.
        missing_models, model_textures, models_present = copy_models(
            needs.models, local_index, search_index, copier)
        texture_names = needs.brush_textures | needs.entity_textures | model_textures

        # 5) Texture names that are your own shaders take their images from
        #    the shader files.
        own_images, remaining = split_custom_shaders(texture_names, own_shaders)

        # 6) Is it already in the project? If a file sits at a wrong place,
        #    offer to move it where the map expects it.
        image_slots = {base: IMAGE_EXTENSIONS for base in remaining | own_images}
        sound_slots = {sound_slot(v): SOUND_EXTENSIONS for v in needs.sounds}
        moved, local_index = offer_corrections(project_dir, image_slots, sound_slots, local_index)

        remaining_missing = {n for n in remaining
                             if not has_asset(local_index, n, IMAGE_EXTENSIONS)}
        own_missing = {b for b in own_images if not has_asset(local_index, b, IMAGE_EXTENSIONS)}
        textures_present = (len(remaining) - len(remaining_missing)
                            + len(own_images) - len(own_missing))

        # 7) Sounds the project does not have yet.
        missing_sounds, sounds_present = copy_sounds(
            needs.sounds, local_index, search_index, copier)

        # 8) Texture names that are shaders defined inside a PK3: the shader
        #    script is copied into scripts/ and the images it uses are exported.
        provided = find_pk3_shaders(search_index, remaining_missing)
        shader_files = {}            # (pk3_path, script path) -> [shader names]
        provided_images = set()
        for name, (pk3_path, real_name, images) in sorted(provided.items()):
            shader_files.setdefault((pk3_path, real_name), []).append(name)
            provided_images |= images
        if provided:
            print(f"[INFO] {len(provided)} texture name(s) are defined by shaders in PK3s "
                  f"({len(shader_files)} shader script(s) will be copied to scripts/).")

        # Everything we should try to find as an image file.
        needed = (remaining_missing - set(provided)) | own_missing | provided_images

        # 9) Shader scripts first, then the images.
        shaders_copied = copy_pk3_shaders(shader_files, copier)
        missing_textures, images_present = copy_texture_images(
            needed, local_index, search_index, copier)
        textures_present += images_present
    finally:
        copier.close()

    # 10) Report.
    already = textures_present + sounds_present + models_present
    if already:
        print(f"\n[INFO] {already} asset(s) were already in your project "
              f"and were left as they are.")
    hint_index = dict(search_index)
    hint_index.update(local_index)
    print_not_found([("textures", missing_textures), ("sounds", missing_sounds),
                     ("models", missing_models)], hint_index)

    # 11) Thumbnail and music: only reported, never changed.
    print()
    check_map_extras(project_dir, map_file.stem, build_local_index(project_dir), search_index)

    moved_text = f", moved {moved} to the expected place" if moved else ""
    print(f"\n[DONE] Copied {copier.copied} file(s) and {shaders_copied} shader script(s)"
          f"{moved_text}, skipped {copier.skipped} that already exist.")
    print("[NOTE] Shader scripts are copied as a whole file, so they may also contain")
    print("       shaders you do not use. Only images of the shaders your map uses")
    print("       are exported.")

# ---------------------------------------------------------------------------
# OPTION 2: RENAME MAP
# ---------------------------------------------------------------------------


def starts_with_base(name: str, base: str) -> bool:
    """True if 'name' belongs to the map called 'base'.

    The character after the base must not be alphanumeric, so that the base
    'mymap_r2' matches 'mymap_r2.bsp' and 'mymap_r2_mini.tga' but NOT
    'mymap_r20.bsp'.
    """
    if not name.startswith(base):
        return False
    return len(name) == len(base) or not name[len(base)].isalnum()


def ask_new_map_name(current_base: str) -> str | None:
    """Ask for the new map name. Returns None if cancelled or not usable."""
    new_base = ask("> Enter new map name: ")
    if new_base == "" or is_cancel(new_base):
        print("[INFO] Renaming cancelled.")
        return None

    # The same rules as for new map folders (letters, digits, '_' and '-').
    error = validate_project_name(new_base)
    if error:
        print(f"[ERROR] {error}")
        return None
    if new_base == current_base:
        print("[INFO] That is already the current name. Nothing to do.")
        return None
    return new_base


def plan_map_renames(project_dir: Path, current_base: str, new_base: str) -> list:
    """List the (old path, new path) pairs that belong to the map.

    That is, in maps/ the .map/.bsp/.mapinfo, extras like '.jpg' and the
    lightmap folder, and in gfx/ the minimap (<name>_mini.tga).
    """
    renames = []
    for sub in ("maps", "gfx"):
        folder = project_dir / sub
        if not folder.is_dir():
            continue
        for entry in sorted(folder.iterdir()):
            if starts_with_base(entry.name, current_base):
                new_name = new_base + entry.name[len(current_base):]
                renames.append((entry, folder / new_name))
    return renames


def find_rename_clashes(project_dir: Path, renames: list, new_folder: Path | None) -> list:
    """Targets that already exist (and are not themselves being renamed)."""
    sources = {src for src, _ in renames}
    clashes = [str(dst.relative_to(project_dir)) for _, dst in renames
               if dst.exists() and dst not in sources]
    if new_folder is not None and new_folder.exists():
        clashes.append(f"{new_folder.name}  (project folder)")
    return clashes


def print_rename_preview(project_dir: Path, renames: list, new_folder: Path | None,
                         new_base: str) -> None:
    """Show everything the rename is going to do, before asking to proceed."""
    print("\nThe following renames will be performed:")
    for src, dst in renames:
        kind = "DIR " if src.is_dir() else "FILE"
        print(f"  [{kind}] {src.relative_to(project_dir)}  ->  {dst.relative_to(project_dir)}")
    if new_folder is not None:
        print(f"  [DIR ] project folder: {project_dir.name}  ->  {new_folder.name}")
    print(f"  [INFO] The title in '{new_base}.mapinfo' will be set to '{new_base}'.")

    # Hint against a doubled prefix in the .pk3 name (the packer adds its own).
    pk3_prefix = load_config().get("pk3_prefix", "")
    if pk3_prefix and new_base.lower().startswith(pk3_prefix.lower()):
        print(f"  [NOTE] The name already starts with your PK3 prefix '{pk3_prefix}'. "
              f"That prefix is added automatically when packing,")
        print(f"         so the .pk3 would be called '{pk3_prefix}{new_base}.pk3'.")


def perform_renames(project_dir: Path, renames: list,
                    new_folder: Path | None) -> tuple | None:
    """Do the renames, files first and the project folder last.

    Stops at the first error so the state stays understandable. Returns
    (folder that now holds the project, new folder name or None), or None if
    a file could not be renamed.
    """
    for src, dst in renames:
        try:
            src.rename(dst)
        except OSError as e:
            print(f"[ERROR] Could not rename '{src.relative_to(project_dir)}': {e}")
            print("        Stopped. Some files may already have been renamed.")
            return None

    if new_folder is None:
        return project_dir, None
    try:
        project_dir.rename(new_folder)
    except OSError as e:
        print(f"[ERROR] Could not rename the project folder: {e}")
        print("        The map files were renamed, the folder keeps its old name.")
        return project_dir, None
    return new_folder, new_folder.name


def find_old_name_leftovers(root: Path, old_base: str) -> list:
    """Things that may still carry the old name.

    They are not renamed on purpose, because other files (shaders, the .map
    itself) refer to them by name.
    """
    leftovers = []
    textures_dir = root / "textures"
    if textures_dir.is_dir():
        for entry in sorted(textures_dir.iterdir()):
            if entry.is_dir() and entry.name.lower() == old_base.lower():
                leftovers.append(f"textures/{entry.name}/")
    scripts_dir = root / "scripts"
    if scripts_dir.is_dir():
        for entry in sorted(scripts_dir.iterdir()):
            if entry.is_file() and old_base.lower() in entry.name.lower():
                leftovers.append(f"scripts/{entry.name}")
    return leftovers


def rename_map(project_dir: Path) -> str | None:
    """Rename the map completely: map files, .mapinfo title and project folder.

    Renames everything that belongs to the current map name (see
    plan_map_renames), sets the .mapinfo title to the new name and renames the
    project folder, so folder and map name stay identical. Shows a preview
    first and asks for confirmation.

    Prefixes and suffixes are NOT part of the map name. The PK3 prefix and the
    revision are added to the .pk3 file name when packing.

    Returns the new project folder name if the folder was renamed, otherwise
    None (the caller then keeps working with the old folder).
    """
    maps_dir = project_dir / "maps"
    if not maps_dir.is_dir():
        print(f"[ERROR] Directory '{maps_dir}' does not exist!")
        return None

    map_file = pick_map_file(maps_dir)
    if map_file is None:
        return None

    current_base = map_file.stem                      # e.g. 'mymap'
    print(f"\n[INFO] Current map name: {current_base}")
    new_base = ask_new_map_name(current_base)
    if new_base is None:
        return None

    renames = plan_map_renames(project_dir, current_base, new_base)
    # The project folder follows the map name.
    new_folder = project_dir.parent / new_base if project_dir.name != new_base else None

    # Refuse to run if a target already exists.
    clashes = find_rename_clashes(project_dir, renames, new_folder)
    if clashes:
        print("[ERROR] These targets already exist, nothing was changed:")
        for name in clashes:
            print(f"  - {name}")
        return None

    print_rename_preview(project_dir, renames, new_folder, new_base)
    if not confirm("\n> Proceed?"):
        print("[INFO] Renaming cancelled. Nothing was changed.")
        return None

    result = perform_renames(project_dir, renames, new_folder)
    if result is None:
        return None
    root, renamed_folder = result

    # Title in the renamed .mapinfo.
    mapinfo_path = root / "maps" / f"{new_base}.mapinfo"
    if mapinfo_path.is_file():
        update_mapinfo_title(mapinfo_path, new_base)
        print(f"  [INFO] Updated the .mapinfo title to '{new_base}'.")
    else:
        print("  [INFO] No .mapinfo found for this map - title not updated.")

    print(f"\n[DONE] Map renamed: {current_base}  ->  {new_base}")

    leftovers = find_old_name_leftovers(root, current_base)
    if leftovers:
        print("  [NOTE] These still use the old name and were NOT renamed (shaders and")
        print("         the .map refer to them by name):")
        for item in leftovers:
            print(f"    - {item}")
    return renamed_folder

# ---------------------------------------------------------------------------
# OPTION 3: PACK MAP
# ---------------------------------------------------------------------------


def is_backup_file(name: str) -> bool:
    """True for editor backups: '*.bak', '*.autosave', '*.autosave.map', ..."""
    lower = name.lower()
    return lower.endswith(".bak") or ".autosave" in lower


def should_pack(rel_path: Path, include_map_source: bool) -> bool:
    """Decide whether a file (given relative to the project) goes into the .pk3."""
    # Skip anything inside an ignored folder such as .git/.
    if any(part in IGNORE_DIRS for part in rel_path.parts[:-1]):
        return False

    name = rel_path.name
    if name in IGNORE_FILES:
        return False

    # Editor backups and autosaves (also catches 'name.autosave.map').
    if is_backup_file(name):
        return False
    if rel_path.suffix.lower() in EXCLUDED_EXTENSIONS:
        return False

    # .map files: only the real map source in maps/ is optional. Stray .map
    # files elsewhere (prefabs, mesh conversions, ...) are never packed.
    if rel_path.suffix.lower() == ".map":
        return include_map_source and rel_path.parts[0] == "maps"

    return True


def split_revision(stem: str, rev_prefix: str) -> tuple:
    """Split a file stem into (core_name, revision_suffix).

    'mymap_r3' with prefix 'r' -> ('mymap', '_r3'). The configured format is
    tried first. If that does not match, a generic '_<letters><digits>' pattern
    is used as fallback (useful after you changed the format). The user always
    sees the result in the preview and has to confirm it.
    """
    rev_prefix = clean_rev_prefix(rev_prefix)
    patterns = (
        rf"_{re.escape(rev_prefix)}\d+[a-z]*$",   # configured format
        r"_[a-z]*\d+[a-z]*$",                      # generic fallback
    )
    for pattern in patterns:
        match = re.search(pattern, stem, re.IGNORECASE)
        if match:
            return stem[:match.start()], match.group(0)
    return stem, ""


def prompt_revision_suffix(prompt: str, rev_prefix: str,
                           default_number: str | None = None) -> str | None:
    """Ask for a suffix and return it as '_<word><number>' (lowercase), or None.

    * A number alone gets the word from the settings: with 'r', '7' -> '_r7'.
    * Anything that starts with a letter is used as typed, so the word can be
      changed too: 'v2' -> '_v2', 'alpha3' -> '_alpha3', '_r12' -> '_r12'.
    None means "cancelled or invalid" (an error message was already printed
    for invalid input). An empty answer uses 'default_number' if one is given.
    """
    text = ask(prompt).lower().lstrip("_")
    if text == "" and default_number is not None:
        return f"_{rev_prefix}{default_number}"
    if text == "" or is_cancel(text):
        return None
    if text in ("h", "s"):
        print(f"[ERROR] '{text}' is a menu command, not a suffix. Nothing was changed.")
        return None
    if not re.fullmatch(r"[a-z0-9]+", text):
        print("[ERROR] The suffix may only contain letters and digits.")
        return None
    return f"_{rev_prefix}{text}" if text[0].isdigit() else f"_{text}"


def find_existing_pk3_revisions(export_dir: Path, pk3_prefix: str, core: str,
                                rev_prefix: str) -> dict:
    """Find already packed revisions of this map in the export folder.

    Looks for files named '<pk3_prefix><core>_<word><number>.pk3' with any
    word (r, v, alpha, ...) and returns {number: (word, file_name)}. If one
    number exists with several words, the word from the settings wins.
    """
    pattern = re.compile(
        rf"^{re.escape(pk3_prefix + core)}_([a-z]*)(\d+)\.pk3$", re.IGNORECASE)
    found = {}
    if export_dir.is_dir():
        for path in sorted(export_dir.glob("*.pk3")):
            match = pattern.match(path.name)
            if not match:
                continue
            word, number = match.group(1).lower(), int(match.group(2))
            if number not in found or word == rev_prefix.lower():
                found[number] = (word, path.name)
    return found


def choose_pk3_revision(export_dir: Path, pk3_prefix: str, base: str,
                        rev_prefix: str) -> tuple | None:
    """Decide the revision suffix of the PK3 file name.

    The map files inside the package keep their names; only the .pk3 file
    name is versioned. Returns (name_part, suffix), where the suffix is ''
    for "no suffix", or None if the user cancelled.

    If a revision is already known - the map files carry one ('mymap_r5') or
    earlier packages of this map exist in the export folder - you are not
    asked whether to add one. Instead you can keep it, raise it by 1, enter
    your own or remove it. Without a known revision you are asked whether to
    add one.
    """
    # If the map files themselves carry a revision ('mymap_r2'), the PK3 name
    # is built from the plain name, otherwise we would get 'mymap_r2_r3'.
    core, name_rev = split_revision(base, rev_prefix)

    existing = find_existing_pk3_revisions(export_dir, pk3_prefix, core, rev_prefix)
    if name_rev:
        print(f"\n[INFO] The map files are named '{base}' (suffix '{name_rev}'). "
              f"The files inside stay unchanged; the PK3 name uses '{core}'.")
        match = re.fullmatch(r"_([a-z]*)(\d+)[a-z]*", name_rev, re.IGNORECASE)
        if match:
            existing.setdefault(int(match.group(2)),
                                (match.group(1).lower(), f"map file name '{base}'"))

    if not existing:
        # Nothing known yet: ask whether the PK3 should get a suffix at all.
        if not confirm("\n> Add a revision number to the PK3 file name?"):
            return core, ""
        suffix = prompt_revision_suffix("> Enter suffix: ", rev_prefix, default_number="1")
        return None if suffix is None else (core, suffix)

    current = max(existing)
    word, source = existing[current]

    def fmt(number):
        return f"_{word}{number}"

    print(f"[INFO] Current revision: {fmt(current)}  (found: {source})")
    print(f"  1) Keep current   ->  {fmt(current)}")
    print(f"  2) Increase by 1  ->  {fmt(current + 1)}")
    print("  3) Enter my own")
    print("  4) Remove it      ->  no suffix")
    choice = ask("> Select option: ").lower()
    if is_cancel(choice):
        return None
    if choice == "1":
        suffix = fmt(current)
    elif choice in ("", "2"):
        suffix = fmt(current + 1)
    elif choice == "3":
        suffix = prompt_revision_suffix("> Enter suffix: ", rev_prefix)
    elif choice == "4":
        suffix = ""
    else:
        print("[ERROR] Invalid selection.")
        return None
    return None if suffix is None else (core, suffix)


def detect_map_name(project_dir: Path, project_name: str) -> tuple | None:
    """Work out the map name that goes into the .pk3 file name.

    The compiled .bsp is preferred (the newest one if there are several), the
    .map source is the fallback. Returns (lowercase name, real spelling for
    messages), or None if there is no .bsp and the user does not want to pack
    anyway.
    """
    maps_dir = project_dir / "maps"
    bsp_files = sorted(maps_dir.glob("*.bsp"), key=lambda p: p.stat().st_mtime, reverse=True) \
        if maps_dir.is_dir() else []
    if bsp_files:
        if len(bsp_files) > 1:
            print(f"[WARNING] Several .bsp files found; using the newest: {bsp_files[0].name}")
        return bsp_files[0].stem.lower(), bsp_files[0].stem

    sources = find_map_sources(maps_dir) if maps_dir.is_dir() else []
    shown_name = sources[0].stem if sources else project_name
    print("[WARNING] No compiled .bsp found in maps/ - the package would not be playable.")
    if not confirm("> Pack anyway?"):
        print("[INFO] Packing cancelled.")
        return None
    return shown_name.lower(), shown_name


def write_pk3(project_dir: Path, output_path: Path, include_map_source: bool) -> int | None:
    """Zip the packable files of the project into 'output_path'.

    Returns the number of packed files, or None if writing failed.
    """
    # Write to a temporary file first, then move it into place. This way a
    # crash or Ctrl+C never leaves a half-written .pk3 behind.
    temp_path = output_path.with_name(output_path.name + ".tmp")
    packed = 0
    try:
        # Deflate is the only compression method Xonotic can read, so we keep it
        # but use the maximum level (9) for the smallest possible file. Packing
        # takes slightly longer, which does not matter for a one-off release build.
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as pk3:
            for file_path in sorted(project_dir.rglob("*")):
                if not file_path.is_file():
                    continue
                rel_path = file_path.relative_to(project_dir)
                if not should_pack(rel_path, include_map_source):
                    continue
                # as_posix() keeps forward slashes, which the PK3 format requires.
                pk3.write(file_path, rel_path.as_posix())
                print(f"  [+] Added: {rel_path.as_posix()}")
                packed += 1
        os.replace(temp_path, output_path)
    except OSError as e:
        print(f"[ERROR] Packing failed: {e}")
        if temp_path.exists():
            temp_path.unlink()
        return None
    return packed


def pack_map(project_dir: Path, project_name: str) -> None:
    """Zip the project folder into a distributable .pk3.

    Steps: find the map name, remind about a missing thumbnail or music, work
    out the file name (prefix + name + revision suffix), then pack.
    """
    config = load_config()
    include_map_source = bool(config.get("include_map_source", True))

    detected = detect_map_name(project_dir, project_name)
    if detected is None:
        return
    map_name_base, shown_name = detected

    # Remind about a missing thumbnail or music file before packing.
    check_map_extras(project_dir, shown_name, build_local_index(project_dir))

    # Work out the target folder and file name: prefix + name (+ revision).
    prefix = config.get("pk3_prefix", "")
    rev_prefix = clean_rev_prefix(config.get("rev_prefix", ""))
    custom_dir = config.get("custom_export_dir")
    export_dir = Path(custom_dir) if custom_dir else project_dir

    selection = choose_pk3_revision(export_dir, prefix, map_name_base, rev_prefix)
    if selection is None:
        print("[INFO] Packing cancelled.")
        return
    pk3_base, revision = selection
    output_name = f"{prefix}{pk3_base}{revision}.pk3"

    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = export_dir / output_name

    # Never replace an existing package without asking.
    if output_path.exists() and not confirm(f"\n> '{output_name}' already exists. Overwrite?"):
        print("[INFO] Packing cancelled. Nothing was changed.")
        return

    print(f"\n[INFO] Packaging contents of '{project_name}'...")
    print(f"[INFO] Target archive: {output_path}")
    print(f"[INFO] Including .map source: {'yes' if include_map_source else 'no'}")

    packed = write_pk3(project_dir, output_path, include_map_source)
    if packed is None:
        return
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n[DONE] Created: {output_path} ({size_mb:.2f} MB)")
    print(f"[SUCCESS] Total files packed: {packed}")

# ---------------------------------------------------------------------------
# SETTINGS MENU
# ---------------------------------------------------------------------------


def show_settings(config: dict) -> None:
    """Print the settings table: one numbered line per setting."""
    export_dir = config.get("custom_export_dir")
    prefix = config.get("pk3_prefix", "")
    rev = config.get("rev_prefix", "")

    print("\n" + "=" * 75)
    print("                  SETTINGS MENU")
    print(get_status_note())
    print("=" * 75)
    print(f"1) PK3 Export Path:      {export_dir or '[Not set - saves inside map folder]'}")
    print(f"2) PK3 Filename Prefix:  {repr(prefix) if prefix else '[Not set - None]'}")
    print(f"3) Revision Format:      {repr(rev) if rev else '[Not set - None]'}")
    search_dirs = config.get("xonotic_dirs") or []
    if search_dirs:
        print(f"4) Search Paths:         {search_dirs[0]}")
        for extra in search_dirs[1:]:
            print(f"                         {extra}")
    else:
        print(f"4) Search Paths:         [Default: {DEFAULT_XONOTIC_DIR}]")
    print(f"5) Include .map in PK3:  {'yes' if config.get('include_map_source') else 'no'}")
    projects_dir = config.get("projects_dir") or f"[Default: {BASE_MAPS_DIR}]"
    print(f"6) Projects Folder:      {projects_dir}")
    print("-" * 75)


def set_export_path(config: dict) -> None:
    """Settings option 1: folder the finished .pk3 files are written to."""
    print("\n--- Set PK3 Export Path ---")
    print(" - Enter an absolute path to save packed PK3s there automatically.")
    print(" - Type 'default' or press Enter to reset to default.")
    value = ask("> Enter path: ")
    if is_cancel(value):
        return
    if value.lower() in ("default", ""):
        config["custom_export_dir"] = None
        save_config(config)
        print("[SUCCESS] Export directory reset to default.")
        return
    new_path = Path(value).expanduser().resolve()
    if not new_path.is_dir():
        print(f"[ERROR] '{new_path}' does not exist or is not a folder!")
        return
    config["custom_export_dir"] = str(new_path)
    save_config(config)
    print(f"[SUCCESS] Custom export directory saved: {new_path}")


def set_pk3_prefix(config: dict) -> None:
    """Settings option 2: text put in front of every generated .pk3 file name."""
    print("\n--- Set PK3 Filename Prefix ---")
    print(" - Enter a prefix for generated PK3 files (e.g. 'duke_').")
    print(" - Press Enter without typing anything to remove the prefix.")
    value = ask("> Enter prefix: ")
    if is_cancel(value):
        return
    # A prefix is part of a file name, so path separators are not allowed.
    if any(ch in value for ch in '/\\:*?"<>|'):
        print("[ERROR] The prefix contains characters that are not allowed in file names.")
        return
    config["pk3_prefix"] = value
    save_config(config)
    print(f"[SUCCESS] PK3 prefix updated to: '{value}'")


def set_revision_format(config: dict) -> None:
    """Settings option 3: the word placed before a revision number ('r', 'v', ...)."""
    print("\n--- Set Revision Format ---")
    print(" - Enter the word placed before a revision number in the PK3 name,")
    print("   e.g. 'r' gives mymap_r3, 'v' gives mymap_v3, 'alpha' gives mymap_alpha3.")
    print(" - Press Enter without typing anything to use plain numbers (mymap_3).")
    value = clean_rev_prefix(ask("> Enter revision prefix: "))
    if is_cancel(value):
        return
    if not re.fullmatch(r"[A-Za-z]*", value):
        print("[ERROR] Only letters are allowed (an underscore is added automatically).")
        return
    config["rev_prefix"] = value
    save_config(config)
    print(f"[SUCCESS] Revision format updated to: '{value}'")


def toggle_map_source(config: dict) -> None:
    """Settings option 5: include the .map source file in the .pk3 or not."""
    config["include_map_source"] = not config.get("include_map_source", True)
    save_config(config)
    state = "included in" if config["include_map_source"] else "left out of"
    print(f"[SUCCESS] The .map source will be {state} the PK3.")


def set_projects_folder(config: dict) -> None:
    """Settings option 6: folder in which map folders are listed and created."""
    print("\n--- Set Projects Folder ---")
    print(" - Folder in which your map folders are listed and new ones are created.")
    print(" - Type 'default' or press Enter to use the folder of this script.")
    value = ask("> Enter path: ")
    if is_cancel(value):
        return
    if value.lower() in ("default", ""):
        config["projects_dir"] = None
        save_config(config)
        print("[SUCCESS] Projects folder reset to the script's folder.")
        return
    new_path = Path(value).expanduser().resolve()
    if not new_path.is_dir():
        # Offer to create it, so a fresh workspace can be set up right here.
        if not confirm(f"'{new_path}' does not exist. Create it?"):
            return
        try:
            new_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"[ERROR] Could not create folder: {e}")
            return
    config["projects_dir"] = str(new_path)
    save_config(config)
    print(f"[SUCCESS] Projects folder saved: {new_path}")


def print_search_paths(shown: list) -> None:
    """Print the search-path editor: explanation, numbered paths and the options."""
    print("\n--- Search Paths for Xonotic assets ---")
    print(" - Missing assets are taken from these folders: first from all .pk3 files")
    print("   below them, then from loose files (the data/ folder, *.pk3dir folders).")
    print(" - The first match wins; the order of the list is the priority.")
    for number, path in enumerate(shown, 1):
        print(f"  {number}) {path}")
    print("  a) Add a path")
    print("  r) Remove a path")
    print("  d) Reset to default")


def add_search_path(config: dict, shown: list) -> None:
    """Ask for a folder and append it to the search paths."""
    value = ask("> Enter path: ")
    if value == "" or is_cancel(value):
        return
    new_path = Path(value).expanduser().resolve()
    if not new_path.is_dir():
        print(f"[ERROR] '{new_path}' does not exist or is not a folder!")
    elif str(new_path) in shown:
        print("[INFO] That path is already in the list.")
    else:
        config["xonotic_dirs"] = shown + [str(new_path)]
        save_config(config)
        print(f"[SUCCESS] Path added: {new_path}")


def remove_search_path(config: dict, shown: list) -> None:
    """Ask for a list number and remove that search path."""
    value = ask("> Enter number: ")
    if value == "" or is_cancel(value):
        return
    if not value.isdigit() or not 1 <= int(value) <= len(shown):
        print("[ERROR] Invalid number!")
        return
    removed = shown.pop(int(value) - 1)
    config["xonotic_dirs"] = shown or None     # never leave the list empty
    save_config(config)
    print(f"[SUCCESS] Path removed: {removed}")


def reset_search_paths(config: dict) -> None:
    """Go back to the default search path (~/.xonotic)."""
    config["xonotic_dirs"] = None
    save_config(config)
    print(f"[SUCCESS] Search paths reset to the default ({DEFAULT_XONOTIC_DIR}).")


def manage_search_paths() -> None:
    """Small menu to add or remove the folders that are searched for assets."""
    while True:
        config = load_config()
        shown = [str(d) for d in get_xonotic_dirs()]
        print_search_paths(shown)
        choice = ask("> Select option: ").lower()

        if choice == "a":
            add_search_path(config, shown)
        elif choice == "r":
            remove_search_path(config, shown)
        elif choice == "d":
            reset_search_paths(config)
        elif choice == "" or is_cancel(choice):
            return
        else:
            print("[ERROR] Invalid option!")


# Menu choice -> action. Every action takes the loaded config dict. The lambdas
# delay the lookup of functions that are defined further down in this file.
SETTINGS_ACTIONS = {
    "1": set_export_path,
    "2": set_pk3_prefix,
    "3": set_revision_format,
    "4": lambda config: manage_search_paths(),
    "5": toggle_map_source,
    "6": set_projects_folder,
    "h": lambda config: show_help(),
}


def settings_menu() -> None:
    """Submenu for the persistent settings; returns when the user goes back."""
    while True:
        config = load_config()
        show_settings(config)
        choice = ask("\n> Select option: ").lower()
        if choice in SETTINGS_ACTIONS:
            SETTINGS_ACTIONS[choice](config)
        elif choice in ("c", "q", ""):
            break
        else:
            print("[ERROR] Invalid option!")

# ---------------------------------------------------------------------------
# HELP SCREEN
# ---------------------------------------------------------------------------


def show_help() -> None:
    """Print a short explanation of every menu entry."""
    config = load_config()
    prefix = config.get("pk3_prefix", "")
    prefix_str = f"'{prefix}'" if prefix else "None"

    print("\n" + "=" * 75)
    print("                      HELP MENU")
    print("=" * 75)
    print("Placement & Execution:")
    print("   Put this script next to your map project folders and run:")
    print("      python3 mapping_helper.py\n")
    print("Start Menu:")
    print("   1) Choose map folder    - pick an existing project by name or number.")
    print("   2) Create new map folder - creates the folder with the standard Xonotic")
    print("      layout (maps, textures, scripts, sound, models, env, gfx).")
    print("   Projects are listed and created in the 'Projects Folder' (settings,")
    print("   default: the folder this script lives in).\n")
    print("1) Export Assets:")
    print("   Scans the .map (brush faces, patches and entity keys like 'model' and")
    print("   'noise') and your scripts/*.shader files and makes sure the project has")
    print("   everything the map uses. For every asset:")
    print("     - already in the project at the expected place: kept as it is")
    print("     - in the project, but at a wrong place: moved there (you confirm)")
    print("     - missing: copied from the search paths (settings, option 4) - first")
    print("       from all .pk3 files below them (support PKs first), then from loose")
    print("       files (data/ folder, *.pk3dir folders)")
    print("   Assets: textures (incl. _glow/_norm/_gloss companions and skybox faces),")
    print("   the shader scripts defining them, sounds, and models with their skins,")
    print("   materials and textures. Existing files are never overwritten.")
    print("   At the end it also reports a missing thumbnail (maps/<name>.jpg) and")
    print("   whether the music named by 'cdtrack' in the .mapinfo is in the project.\n")
    print("2) Rename Map:")
    print("   Renames the map completely: files and lightmap folder in maps/, the")
    print("   .mapinfo title and the project folder. Shows a preview first. Prefixes")
    print("   and suffixes are not part of the map name - they only exist for the")
    print("   .pk3 (settings 2 and 3).\n")
    print("3) Pack it:")
    print(f"   Builds a .pk3 from the project (prefix: {prefix_str}). Compiler leftovers,")
    print("   backups and working files (.prt, .srf, .xcf, ...) are left out. The")
    print("   maps/*.map source is included unless disabled in the settings.")
    print("   Before packing it warns about a missing thumbnail (maps/<name>.jpg) and")
    print("   about music from the .mapinfo ('cdtrack') that is not in the project.")
    print("   If the map name or an earlier .pk3 already has a revision suffix, you can")
    print("   keep it, raise it by 1, enter your own or remove it. Otherwise you are")
    print("   asked whether the .pk3 name should get one. Your own suffix: a number")
    print("   gets the word from the settings (2 -> _r2), anything starting with a")
    print("   letter is used as typed (v2 -> _v2). The map files inside the package")
    print("   keep their names.\n")
    print("Global Commands:")
    print("   h = help | s = settings | c = cancel / back | q = quit")
    print("=" * 75)

# ---------------------------------------------------------------------------
# PROJECT MENUS & MAIN LOOP
# ---------------------------------------------------------------------------


def list_projects() -> list[str]:
    """Return the names of all folders in the projects folder that contain 'maps/'."""
    workspace = get_workspace_dir()
    if not workspace.is_dir():
        return []
    return sorted(
        p.name for p in workspace.iterdir()
        if p.is_dir() and (p / "maps").is_dir() and p.name not in IGNORE_DIRS
    )


def print_header() -> None:
    """Print banner + status note."""
    print("=" * 75)
    print(ASCII_BANNER)
    print(get_status_note())
    print("=" * 75)


def print_main_menu() -> None:
    """Print the start menu together with the active projects folder."""
    workspace = get_workspace_dir()
    print("\n" + "=" * 75)
    print("MAIN MENU")
    print(f"  Projects folder: {workspace}")
    if not workspace.is_dir():
        print("  [WARNING] This folder does not exist - change it in the settings (s).")
    print("=" * 75)
    print("1) Choose map folder")
    print("2) Create new map folder")


def ask_new_project_name() -> tuple | None:
    """Prompt for the name of a new map folder.

    Loops so that help/settings can be used from this prompt and we come back
    here afterwards. The projects folder is re-read each time because the
    settings may have changed it. Returns (projects folder, name), or None if
    the user cancelled or there is no usable projects folder.
    """
    while True:
        workspace = get_workspace_dir()
        if not workspace.is_dir():
            print(f"[ERROR] Projects folder '{workspace}' does not exist!")
            print("        Change it in the settings (press 's').")
            return None

        print("\n--- Create new map folder ---")
        print(f" - It will be created in: {workspace}")
        print(" - Allowed characters: letters, digits, '_' and '-'.")
        name = ask("> Enter new map folder name: ")
        lower = name.lower()

        # Menu commands are handled here and are never used as a folder name.
        if lower == "q":
            print("\nGoodbye!")
            sys.exit(0)
        elif lower == "h":
            show_help()
        elif lower == "s":
            settings_menu()
        elif lower in ("c", "x"):
            print("[INFO] Cancelled.")
            return None
        elif lower != "":
            return workspace, name


def make_project_folders(project_dir: Path) -> bool:
    """Create the project folder with the standard Xonotic sub-folders."""
    try:
        project_dir.mkdir()
        for subdir in NEW_PROJECT_SUBDIRS:
            (project_dir / subdir).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[ERROR] Could not create the folder structure: {e}")
        return False
    return True


def create_project() -> str | None:
    """Create a new map folder with the standard Xonotic sub-folders.

    Returns the new project's folder name (so the caller can open it right
    away), or None if nothing was created.
    """
    asked = ask_new_project_name()
    if asked is None:
        return None
    workspace, name = asked

    error = validate_project_name(name)
    if error:
        print(f"[ERROR] {error}")
        return None

    project_dir = workspace / name
    if project_dir.exists():
        print(f"[ERROR] '{project_dir}' already exists - nothing was changed.")
        # Convenience: if it is a folder, offer to simply open it.
        if project_dir.is_dir() and confirm("> Open the existing folder instead?"):
            return name
        return None

    if not make_project_folders(project_dir):
        return None

    print(f"\n[DONE] Created map folder: {project_dir}")
    for subdir in NEW_PROJECT_SUBDIRS:
        print(f"  [DIR] {name}/{subdir}/")
    return name


def print_project_list(workspace: Path, projects: list) -> None:
    """Print the numbered list of existing map folders (or a hint if there are none)."""
    if projects:
        print("\nProjects found:")
        for i, name in enumerate(projects, start=1):
            print(f"  {i}) {name}")
    else:
        print(f"\n[INFO] No map folders found yet in '{workspace}'.")


def resolve_project_entry(entry: str, workspace: Path, projects: list) -> str | None:
    """Turn what the user typed into a project folder name (or None, with an error)."""
    # Only direct sub-folders are allowed - no paths like '../other'.
    if entry in (".", "..") or Path(entry).name != entry:
        print("[ERROR] Please enter just the folder name, not a path.")
        return None

    # An exact folder name always wins; otherwise treat digits as list number.
    if (workspace / entry).is_dir():
        return entry
    if entry.isdigit() and 1 <= int(entry) <= len(projects):
        return projects[int(entry) - 1]

    print(f"[ERROR] Project directory '{workspace / entry}' not found!")
    return None


def choose_project() -> str | None:
    """Let the user pick an existing map folder by name or by list number.

    Returns the folder name, or None if the user went back to the main menu.
    """
    while True:
        workspace = get_workspace_dir()
        projects = list_projects()
        print_project_list(workspace, projects)

        entry = ask("\n> Enter map directory name or number: ")
        lower = entry.lower()

        if lower == "q":
            sys.exit(0)
        elif lower == "h":
            show_help()
        elif lower == "s":
            settings_menu()          # the projects folder may have changed
        elif lower == "c":
            return None
        elif lower != "":
            chosen = resolve_project_entry(entry, workspace, projects)
            if chosen is not None:
                return chosen


def project_menu(map_name: str) -> None:
    """Action menu for one project. Returns when the user presses 'c'."""
    project_dir = get_workspace_dir() / map_name

    while True:
        print("\n" + "=" * 75)
        print(f"Active Project: {map_name}")
        print(get_status_note(project_dir))
        print("=" * 75)
        print("1) Export Assets")
        print("2) Rename Map")
        print("3) Pack it")

        choice = ask("\n> Select option: ").lower()

        if choice == "1":
            export_assets(project_dir)
        elif choice == "2":
            new_name = rename_map(project_dir)
            if new_name:
                # The project folder was renamed: continue with the new one.
                map_name = new_name
                project_dir = get_workspace_dir() / map_name
        elif choice == "3":
            pack_map(project_dir, map_name)
        elif choice == "s":
            settings_menu()
        elif choice == "h":
            show_help()
        elif choice == "c":
            print("[INFO] Returning to main menu...")
            return
        elif choice == "q":
            print("\nGoodbye!")
            sys.exit(0)
        else:
            print("[ERROR] Invalid option!")


def main() -> None:
    """Start menu: choose an existing map folder or create a new one."""
    print_header()

    while True:
        print_main_menu()
        choice = ask("\n> Select option: ").lower()

        project = None
        if choice == "1":
            project = choose_project()
        elif choice == "2":
            project = create_project()
        elif choice == "h":
            show_help()
        elif choice == "s":
            settings_menu()
            print_header()
        elif choice == "q":
            print("\nGoodbye!")
            sys.exit(0)
        elif choice in ("c", ""):
            continue
        else:
            print("[ERROR] Invalid option!")

        # A chosen or freshly created project opens its action menu right away.
        if project:
            project_menu(project)


if __name__ == "__main__":
    main()
