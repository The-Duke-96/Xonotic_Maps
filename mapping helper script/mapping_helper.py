#!/usr/bin/env python3
"""
XONOTIC MAPPING HELPER
======================

A small, dependency-free terminal tool for Xonotic mappers. It takes care of
the boring parts of a map project:

  1) Export Textures  - scan your .map file (classic and brush-primitive format,
                        brush faces + patches) and your own
                        shader scripts, then copy every texture that is found in
                        the Xonotic "mapping support" PK3s into your project.
  2) Change Revision  - rename the map files, the lightmap folder and update the
                        title in the .mapinfo, with a preview + confirmation.
  3) Clean Backups    - remove leftover editor backups (.bak / .autosave).
  4) Pack it          - build a ready-to-distribute .pk3 (the .map source can be
                        included so other people can open the map in NetRadiant).

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
    * Revision format       - e.g. 'r' -> mymap_r3
    * Xonotic data folder   - where the support PK3s are searched
    * Include .map source   - ship the editable .map inside the .pk3 (default: yes)
    * Projects folder       - where map folders are listed and created
                              (default: the folder this script lives in)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

# Enable arrow keys, cursor movement and input history for input() on
# Linux/macOS. The 'readline' module is not available on Windows by default,
# where the console handles this natively, so a failed import is fine.
try:
    import readline  # noqa: F401  (imported for its side effect only)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# CONSTANTS & PATHS
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
    "xonotic_data_dir": None,     # None = auto-detect (see get_xonotic_data_dir)
    "include_map_source": True,   # ship maps/*.map inside the .pk3
    "projects_dir": None,         # None = the folder this script lives in
}

# Places where Xonotic keeps the user's data folder. The first existing one wins.
XONOTIC_DATA_CANDIDATES = [
    Path.home() / ".xonotic" / "data",                              # Linux
    Path.home() / "Saved Games" / "xonotic" / "data",               # Windows
    Path.home() / "Library" / "Application Support" / "xonotic" / "data",  # macOS
]

# Image formats the engine can load for textures.
IMAGE_EXTENSIONS = [".png", ".tga", ".jpg", ".dds"]

# Companion images that belong to a texture (glow, normal map, gloss, ...).
# The empty string is the plain diffuse texture itself.
MAP_SUFFIXES = [
    "", "_alpha", "_gloss", "_glow", "_glow_alpha",
    "_norm", "_norm_alpha", "_pants", "_shirt",
]

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

# ASCII art banner for the title screen.
ASCII_BANNER = r"""
  __  __                  _               _   _         _
 |  \/  | __ _ _ __  _ __(_)_ __   __ _  | | | | ___ __| | ___  _ __
 | |\/| |/ _` | '_ \| '_ \ | '_ \ / _` | | |_| |/ _ \/ _` |/ _ \| '__|
 | |  | | (_| | |_) | |_) | | | | | (_| | |  _  |  __/ (_| | (_) | |
 |_|  |_|\__,_| .__/| .__/|_|_| |_|\__, | |_| |_|\___|\__,_|\___/|_|
              |_|   |_|             |___/
"""


# ---------------------------------------------------------------------------
# SMALL INPUT HELPERS
# ---------------------------------------------------------------------------
def ask(prompt):
    """Read one line from the user. Ctrl+C / Ctrl+D quit the program cleanly."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye!")
        sys.exit(0)


def confirm(question):
    """Ask a yes/no question. Anything except 'y' / 'yes' counts as 'no'."""
    return ask(f"{question} [y/N]: ").lower() in ("y", "yes")


# ---------------------------------------------------------------------------
# CONFIG PERSISTENCE
# ---------------------------------------------------------------------------
def load_config():
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


def save_config(config):
    """Write the settings dictionary to the JSON file next to the script."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except OSError as e:
        print(f"[ERROR] Could not save configuration file: {e}")


def clean_rev_prefix(value):
    """Normalize the revision prefix: '_r', 'r' and ' r ' all become 'r'."""
    return (value or "").strip().lstrip("_")


def get_xonotic_data_dir():
    """Return the Xonotic data folder: the configured one, else the first
    existing default location, else the Linux default (even if missing)."""
    configured = load_config().get("xonotic_data_dir")
    if configured:
        return Path(configured)
    for candidate in XONOTIC_DATA_CANDIDATES:
        if candidate.is_dir():
            return candidate
    return XONOTIC_DATA_CANDIDATES[0]


def get_workspace_dir():
    """Return the folder in which map project folders are listed and created.

    This is the 'Projects folder' setting. If it is not set, the folder the
    script lives in is used, because the tool is designed to sit next to your
    map projects.
    """
    configured = load_config().get("projects_dir")
    return Path(configured) if configured else BASE_MAPS_DIR


def get_status_note(project_dir=None):
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
# GENERAL HELPERS
# ---------------------------------------------------------------------------
def get_support_pk3_files():
    """Find the support PK3s in the Xonotic data folder.

    A file counts as 'support' if its name contains 'mapping' or 'extra'
    (e.g. xonotic-*-mapping.pk3, xonotic-*-extra.pk3). Sorted by name so the
    result - and therefore the search priority - is stable between runs.
    """
    data_dir = get_xonotic_data_dir()
    if not data_dir.is_dir():
        return []
    result = []
    for pk3_path in sorted(data_dir.glob("*.pk3")):
        name = pk3_path.name.lower()
        if "mapping" in name or "extra" in name:
            result.append(pk3_path)
    return result


def build_pk3_index(pk3_paths):
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


def find_map_sources(maps_dir):
    """Return all real .map source files in maps/ (newest first).

    Editor autosaves such as 'name.autosave.map' are ignored.
    """
    candidates = [
        p for p in maps_dir.glob("*.map")
        if p.is_file() and ".autosave" not in p.name.lower()
    ]
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)


def pick_map_file(maps_dir):
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
    choice = ask(f"> Select file [1-{len(candidates)}] (Enter = 1, c = cancel): ").lower()
    if choice in ("c", "x", "q"):
        print("[INFO] Cancelled.")
        return None
    if choice == "":
        return candidates[0]
    if choice.isdigit() and 1 <= int(choice) <= len(candidates):
        return candidates[int(choice) - 1]
    print("[ERROR] Invalid selection.")
    return None


# ---------------------------------------------------------------------------
# OPTION 1: EXPORT TEXTURES
# ---------------------------------------------------------------------------
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


def strip_image_extension(name):
    """Remove a trailing .tga/.png/.jpg/.dds from a texture reference."""
    for ext in IMAGE_EXTENSIONS:
        if name.endswith(ext):
            return name[:-len(ext)]
    return name


def normalize_brush_texture(name):
    """Turn a texture name from a .map file into 'textures/<name>' (lowercase).

    Radiant stores names without the implicit 'textures/' folder, so we add it
    unless it is already there. File extensions are removed.
    """
    name = strip_image_extension(name.lower().replace("\\", "/"))
    return name if name.startswith("textures/") else f"textures/{name}"


def extract_used_textures(map_file_path):
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


def parse_shader_file(shader_path):
    """Read a .shader script and return (defined_shader_names, referenced_images).

    defined_shader_names - names declared at brace depth 0, e.g.
                           'textures/mymap/lamp'. Brush faces using these names
                           are custom shaders, not plain image files.
    referenced_images    - image paths used inside the shaders by 'map',
                           'clampmap', 'animmap' and 'skyparms' (skybox faces
                           are expanded to the six _rt/_lf/... images).
    """
    defined, referenced = set(), set()
    depth = 0

    with open(shader_path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.split("//", 1)[0].strip()      # drop comments
            if not line:
                continue
            tokens = line.split()

            if depth == 0:
                # Outside any braces a line is the name of a new shader.
                if tokens[0] not in ("{", "}"):
                    defined.add(strip_image_extension(tokens[0].lower().replace("\\", "/")))
            else:
                key = tokens[0].lower()
                if key in ("map", "clampmap") and len(tokens) > 1:
                    if not tokens[1].startswith("$"):      # skip $lightmap etc.
                        referenced.add(strip_image_extension(tokens[1].lower()))
                elif key == "animmap":
                    # Syntax: animmap <fps> <image1> <image2> ...
                    for token in tokens[2:]:
                        referenced.add(strip_image_extension(token.lower()))
                elif key == "skyparms" and len(tokens) > 1 and tokens[1] != "-":
                    base = tokens[1].lower()
                    for suffix in SKY_FACE_SUFFIXES:
                        referenced.add(base + suffix)

            # Track brace depth AFTER handling the line itself.
            depth = max(0, depth + line.count("{") - line.count("}"))

    return defined, referenced


def export_textures(project_dir):
    """Copy all needed textures from the support PK3s into the project folder.

    Existing files in the project are never overwritten, so your own edited
    textures are safe.
    """
    maps_dir = project_dir / "maps"
    if not maps_dir.is_dir():
        print(f"[ERROR] Subfolder '{maps_dir}' does not exist!")
        return

    map_file = pick_map_file(maps_dir)
    if map_file is None:
        return
    print(f"\n[INFO] Analyzing map file: {map_file.name}...")

    # 1) What does the map use?
    brush_textures = extract_used_textures(map_file)
    print(f"[SUCCESS] Found {len(brush_textures)} unique textures in the .map file.")

    # 2) Which of those are custom shaders of this project, and what do those
    #    shaders reference themselves?
    defined_shaders, shader_images = set(), set()
    scripts_dir = project_dir / "scripts"
    if scripts_dir.is_dir():
        for shader_file in sorted(scripts_dir.glob("*.shader")):
            defined, referenced = parse_shader_file(shader_file)
            defined_shaders |= defined
            shader_images |= referenced
            print(f"[INFO] Parsed shader script: {shader_file.name} "
                  f"({len(defined)} shaders, {len(referenced)} image references)")

    custom = {t for t in brush_textures if t in defined_shaders}
    if custom:
        print(f"[INFO] {len(custom)} texture name(s) are your own shaders "
              f"(images are taken from the shader files instead).")

    # Everything we should try to find as an image file.
    needed = (brush_textures - custom) | shader_images

    # 3) Where can we get images from?
    support_pk3s = get_support_pk3_files()
    if not support_pk3s:
        print(f"[ERROR] No support PK3s found in '{get_xonotic_data_dir()}'!")
        print("        Set the correct folder in the settings menu (press 's').")
        return
    print(f"[INFO] Scanning {len(support_pk3s)} support archive(s): "
          f"{[p.name for p in support_pk3s]}")
    index = build_pk3_index(support_pk3s)

    # 4) Copy everything we can find.
    project_root = project_dir.resolve()
    copied = skipped = 0
    missing = []
    open_archives = {}      # keep each PK3 open while copying, close at the end

    try:
        for image_base in sorted(needed):
            found = False
            # Try the plain texture plus every companion map, in every format.
            for suffix in MAP_SUFFIXES:
                for ext in IMAGE_EXTENSIONS:
                    hit = index.get(f"{image_base}{suffix}{ext}")
                    if hit is None:
                        continue
                    found = True
                    pk3_path, real_name = hit
                    target = project_dir / real_name

                    # Safety: never write outside the project folder, even if
                    # an archive contains a malicious '../' path.
                    if project_root not in target.resolve().parents:
                        continue
                    # Never overwrite files the user already has.
                    if target.exists():
                        skipped += 1
                        continue

                    if pk3_path not in open_archives:
                        open_archives[pk3_path] = zipfile.ZipFile(pk3_path, "r")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with open_archives[pk3_path].open(real_name) as src, \
                            open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    print(f"  [+] Copied ({pk3_path.name}): {real_name}")
                    copied += 1
            if not found:
                missing.append(image_base)
    finally:
        for archive in open_archives.values():
            archive.close()

    # 5) Report.
    if missing:
        print("\n[INFO] No matching image found in the support PK3s for:")
        for name in missing:
            print(f"  [?] {name}")
        print("      These are usually shipped with the base game or defined by a")
        print("      shader (check any that you expected to be exported).")

    print(f"\n[DONE] Copied {copied} file(s), skipped {skipped} that already exist.")
    print("[NOTE] Shader scripts from the support PKs are not copied - if a")
    print("       texture relies on one, add that .shader file to your scripts/ folder.")


# ---------------------------------------------------------------------------
# OPTION 2: CHANGE REVISION
# ---------------------------------------------------------------------------
def split_revision(stem, rev_prefix):
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


def starts_with_base(name, base):
    """True if 'name' belongs to the map called 'base'.

    The character after the base must not be alphanumeric, so that the base
    'mymap_r2' matches 'mymap_r2.bsp' and 'mymap_r2_mini.tga' but NOT
    'mymap_r20.bsp'.
    """
    if not name.startswith(base):
        return False
    return len(name) == len(base) or not name[len(base)].isalnum()


def update_mapinfo_title(mapinfo_path, core, old_rev, new_rev):
    """Rewrite the 'title' line of a .mapinfo so it ends with the new revision.

    Only the title line is touched. Encoding errors and line endings are
    preserved byte-for-byte ('surrogateescape' + newline='').
    """
    with open(mapinfo_path, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        lines = f.readlines()

    # Matches e.g. 'title Space Hangar _r2' -> groups: 'title ', value, trailing
    title_re = re.compile(r"^(\s*title\s+)(.*?)(\s*)$", re.IGNORECASE)
    found = False
    for i, line in enumerate(lines):
        match = title_re.match(line)
        if match and not found:
            found = True
            value = match.group(2)
            # Remove the old revision from the end of the title (if present).
            if old_rev and value.endswith(old_rev):
                value = value[:-len(old_rev)].rstrip()
            lines[i] = f"{match.group(1)}{value} {new_rev}{match.group(3)}"

    if not found:
        # No title yet: add one, making sure the previous line is terminated.
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += "\n"
        lines.append(f"title {core} {new_rev}\n")

    with open(mapinfo_path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.writelines(lines)


def change_revision(project_dir):
    """Rename all files/folders of the map to a new revision tag.

    Steps: detect the current name -> ask for the new tag -> show a preview ->
    ask for confirmation -> rename -> update the .mapinfo title.
    """
    maps_dir = project_dir / "maps"
    if not maps_dir.is_dir():
        print(f"[ERROR] Directory '{maps_dir}' does not exist!")
        return

    prefix = clean_rev_prefix(load_config().get("rev_prefix", ""))

    map_file = pick_map_file(maps_dir)
    if map_file is None:
        return

    current_base = map_file.stem                      # e.g. 'mymap_r2'
    core, old_rev = split_revision(current_base, prefix)
    print(f"\n[INFO] Current name: {current_base}  "
          f"(base: '{core}', revision: '{old_rev or 'none'}')")

    tag = ask("> Enter new revision tag (e.g. 3): ").lower().lstrip("_")
    if tag in ("c", "x", "q", ""):
        print("[INFO] Revision change cancelled.")
        return

    # Allow typing the prefix too: with prefix 'r', both '3' and 'r3' work.
    if prefix and tag.startswith(prefix.lower()) and tag[len(prefix):][:1].isdigit():
        tag = tag[len(prefix):]
    if not re.fullmatch(r"[a-z0-9]+", tag):
        print("[ERROR] The tag may only contain letters and digits.")
        return

    new_rev = f"_{prefix}{tag}"
    new_base = f"{core}{new_rev}"
    if new_base == current_base:
        print("[INFO] That is already the current revision. Nothing to do.")
        return

    # Collect everything in maps/ that belongs to the current base name:
    # the .map/.bsp/.mapinfo, extras like '_mini.tga', and the lightmap folder.
    renames = []
    for entry in sorted(maps_dir.iterdir()):
        if starts_with_base(entry.name, current_base):
            new_name = new_base + entry.name[len(current_base):]
            renames.append((entry, maps_dir / new_name))

    # Refuse to run if a target already exists (and is not itself being renamed).
    sources = {src for src, _ in renames}
    clashes = [dst for _, dst in renames if dst.exists() and dst not in sources]
    if clashes:
        print("[ERROR] These targets already exist, nothing was changed:")
        for dst in clashes:
            print(f"  - {dst.name}")
        return

    # Preview.
    print("\nThe following renames will be performed:")
    for src, dst in renames:
        kind = "DIR " if src.is_dir() else "FILE"
        print(f"  [{kind}] {src.name}  ->  {dst.name}")
    print(f"  [INFO] The title in '{new_base}.mapinfo' (if present) will end with '{new_rev}'.")
    if not confirm("\n> Proceed?"):
        print("[INFO] Revision change cancelled. Nothing was changed.")
        return

    # Do the renames. Stop at the first error so the state stays understandable.
    for src, dst in renames:
        try:
            src.rename(dst)
        except OSError as e:
            print(f"[ERROR] Could not rename '{src.name}': {e}")
            print("        Stopped. Some files may already have been renamed.")
            return

    # Update the title in the renamed .mapinfo.
    mapinfo_path = maps_dir / f"{new_base}.mapinfo"
    if mapinfo_path.is_file():
        update_mapinfo_title(mapinfo_path, core, old_rev, new_rev)
        print(f"  [INFO] Updated .mapinfo title with '{new_rev}'.")
    else:
        print("  [INFO] No .mapinfo found for this map - title not updated.")

    print(f"\n[DONE] Revision successfully updated to '{new_rev}'.")


# ---------------------------------------------------------------------------
# OPTION 3: CLEAN BACKUPS
# ---------------------------------------------------------------------------
def is_backup_file(name):
    """True for editor backups: '*.bak', '*.autosave', '*.autosave.map', ..."""
    lower = name.lower()
    return lower.endswith(".bak") or ".autosave" in lower


def clean_backups(project_dir):
    """Delete leftover .bak / .autosave files in maps/ after confirmation."""
    maps_dir = project_dir / "maps"
    if not maps_dir.is_dir():
        print(f"[ERROR] Directory '{maps_dir}' does not exist!")
        return

    backups = sorted(p for p in maps_dir.iterdir() if p.is_file() and is_backup_file(p.name))
    if not backups:
        print("\n[INFO] No backup files found.")
        return

    print("\nThe following backup files will be deleted:")
    for path in backups:
        print(f"  - {path.name}")
    print("  (Tip: an .autosave can be your last rescue after an editor crash.)")
    if not confirm("\n> Delete these files?"):
        print("[INFO] Nothing was deleted.")
        return

    deleted = 0
    for path in backups:
        try:
            path.unlink()
            print(f"  [DEL] Removed: {path.name}")
            deleted += 1
        except OSError as e:
            print(f"  [ERROR] Could not delete {path.name}: {e}")
    print(f"\n[DONE] Cleaned up {deleted} backup file(s).")


# ---------------------------------------------------------------------------
# OPTION 4: PACK MAP
# ---------------------------------------------------------------------------
def should_pack(rel_path, include_map_source):
    """Decide whether a file (given relative to the project) goes into the .pk3."""
    # Skip anything inside an ignored folder such as .git/.
    if any(part in IGNORE_DIRS for part in rel_path.parts[:-1]):
        return False

    name = rel_path.name
    lower = name.lower()
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


def pack_map(project_dir, project_name):
    """Zip the project folder into a distributable .pk3."""
    maps_dir = project_dir / "maps"
    config = load_config()
    include_map_source = bool(config.get("include_map_source", True))

    # Determine the map name for the file name: prefer the compiled .bsp.
    map_name_base = project_name.lower()
    bsp_files = sorted(maps_dir.glob("*.bsp"), key=lambda p: p.stat().st_mtime, reverse=True) \
        if maps_dir.is_dir() else []
    if bsp_files:
        map_name_base = bsp_files[0].stem.lower()
        if len(bsp_files) > 1:
            print(f"[WARNING] Several .bsp files found; using the newest: {bsp_files[0].name}")
    else:
        sources = find_map_sources(maps_dir) if maps_dir.is_dir() else []
        if sources:
            map_name_base = sources[0].stem.lower()
        print("[WARNING] No compiled .bsp found in maps/ - the package would not be playable.")
        if not confirm("> Pack anyway?"):
            print("[INFO] Packing cancelled.")
            return

    # Build the output path from prefix + name, in the configured folder.
    prefix = config.get("pk3_prefix", "")
    output_name = f"{prefix}{map_name_base}.pk3"
    custom_dir = config.get("custom_export_dir")
    export_dir = Path(custom_dir) if custom_dir else project_dir
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = export_dir / output_name

    print(f"\n[INFO] Packaging contents of '{project_name}'...")
    print(f"[INFO] Target archive: {output_path}")
    print(f"[INFO] Including .map source: {'yes' if include_map_source else 'no'}")

    # Write to a temporary file first, then move it into place. This way a
    # crash or Ctrl+C never leaves a half-written .pk3 behind.
    temp_path = export_dir / (output_name + ".tmp")
    packed = 0
    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as pk3:
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
        return

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n[DONE] Created: {output_path} ({size_mb:.2f} MB)")
    print(f"[SUCCESS] Total files packed: {packed}")


# ---------------------------------------------------------------------------
# SETTINGS MENU
# ---------------------------------------------------------------------------
def settings_menu():
    """Submenu for the persistent settings."""
    while True:
        config = load_config()
        export_dir = config.get("custom_export_dir")
        prefix = config.get("pk3_prefix", "")
        rev = config.get("rev_prefix", "")
        data_dir = config.get("xonotic_data_dir")

        print("\n" + "=" * 75)
        print("                  SETTINGS MENU")
        print(get_status_note())
        print("=" * 75)
        print(f"1) PK3 Export Path:      {export_dir or '[Not set - saves inside map folder]'}")
        print(f"2) PK3 Filename Prefix:  {repr(prefix) if prefix else '[Not set - None]'}")
        print(f"3) Revision Format:      {repr(rev) if rev else '[Not set - None]'}")
        print(f"4) Xonotic Data Folder:  {data_dir or f'[Auto-detect: {get_xonotic_data_dir()}]'}")
        print(f"5) Include .map in PK3:  {'yes' if config.get('include_map_source') else 'no'}")
        print(f"6) Projects Folder:      {config.get('projects_dir') or f'[Default: {BASE_MAPS_DIR}]'}")
        print("-" * 75)

        choice = ask("\n> Select option: ").lower()

        if choice == "1":
            print("\n--- Set PK3 Export Path ---")
            print(" - Enter an absolute path to save packed PK3s there automatically.")
            print(" - Type 'default' or press Enter to reset to default.")
            value = ask("> Enter path: ")
            if value.lower() in ("c", "x", "q"):
                continue
            if value.lower() in ("default", ""):
                config["custom_export_dir"] = None
                save_config(config)
                print("[SUCCESS] Export directory reset to default.")
            else:
                new_path = Path(value).expanduser().resolve()
                if not new_path.is_dir():
                    print(f"[ERROR] '{new_path}' does not exist or is not a folder!")
                else:
                    config["custom_export_dir"] = str(new_path)
                    save_config(config)
                    print(f"[SUCCESS] Custom export directory saved: {new_path}")

        elif choice == "2":
            print("\n--- Set PK3 Filename Prefix ---")
            print(" - Enter a prefix for generated PK3 files (e.g. 'duke_').")
            print(" - Press Enter without typing anything to remove the prefix.")
            value = ask("> Enter prefix: ")
            if value.lower() in ("c", "x", "q"):
                continue
            # A prefix is part of a file name, so path separators are not allowed.
            if any(ch in value for ch in '/\\:*?"<>|'):
                print("[ERROR] The prefix contains characters that are not allowed in file names.")
                continue
            config["pk3_prefix"] = value
            save_config(config)
            print(f"[SUCCESS] PK3 prefix updated to: '{value}'")

        elif choice == "3":
            print("\n--- Set Revision Format ---")
            print(" - Enter the letters placed before the revision number,")
            print("   e.g. 'r' gives mymap_r3, 'v' gives mymap_v3.")
            print(" - Press Enter without typing anything to use plain numbers (mymap_3).")
            value = clean_rev_prefix(ask("> Enter revision prefix: "))
            if value.lower() in ("c", "x", "q"):
                continue
            if not re.fullmatch(r"[A-Za-z]*", value):
                print("[ERROR] Only letters are allowed (an underscore is added automatically).")
                continue
            config["rev_prefix"] = value
            save_config(config)
            print(f"[SUCCESS] Revision format updated to: '{value}'")

        elif choice == "4":
            print("\n--- Set Xonotic Data Folder ---")
            print(" - Folder that contains your support PK3s (e.g. ~/.xonotic/data).")
            print(" - Type 'default' or press Enter to use auto-detection.")
            value = ask("> Enter path: ")
            if value.lower() in ("c", "x", "q"):
                continue
            if value.lower() in ("default", ""):
                config["xonotic_data_dir"] = None
                save_config(config)
                print("[SUCCESS] Using auto-detection again.")
            else:
                new_path = Path(value).expanduser().resolve()
                if not new_path.is_dir():
                    print(f"[ERROR] '{new_path}' does not exist or is not a folder!")
                else:
                    config["xonotic_data_dir"] = str(new_path)
                    save_config(config)
                    print(f"[SUCCESS] Xonotic data folder saved: {new_path}")

        elif choice == "5":
            # Simple toggle.
            config["include_map_source"] = not config.get("include_map_source", True)
            save_config(config)
            state = "included in" if config["include_map_source"] else "left out of"
            print(f"[SUCCESS] The .map source will be {state} the PK3.")

        elif choice == "6":
            print("\n--- Set Projects Folder ---")
            print(" - Folder in which your map folders are listed and new ones are created.")
            print(" - Type 'default' or press Enter to use the folder of this script.")
            value = ask("> Enter path: ")
            if value.lower() in ("c", "x", "q"):
                continue
            if value.lower() in ("default", ""):
                config["projects_dir"] = None
                save_config(config)
                print("[SUCCESS] Projects folder reset to the script's folder.")
            else:
                new_path = Path(value).expanduser().resolve()
                if not new_path.is_dir():
                    # Offer to create it, so a fresh workspace can be set up here.
                    if not confirm(f"'{new_path}' does not exist. Create it?"):
                        continue
                    try:
                        new_path.mkdir(parents=True, exist_ok=True)
                    except OSError as e:
                        print(f"[ERROR] Could not create folder: {e}")
                        continue
                config["projects_dir"] = str(new_path)
                save_config(config)
                print(f"[SUCCESS] Projects folder saved: {new_path}")

        elif choice in ("c", "q", ""):
            break
        else:
            print("[ERROR] Invalid option!")


# ---------------------------------------------------------------------------
# HELP SCREEN
# ---------------------------------------------------------------------------
def show_help():
    """Print a short explanation of every menu entry."""
    config = load_config()
    prefix = config.get("pk3_prefix", "")
    rev = config.get("rev_prefix", "")
    prefix_str = f"'{prefix}'" if prefix else "None"
    rev_str = f"'{rev}'" if rev else "None"

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
    print("1) Export Textures:")
    print("   Scans the .map (brush faces + patches) and your scripts/*.shader files")
    print("   and copies the matching textures - including _glow, _norm, _gloss, ...")
    print("   companions and skybox faces - from the support PKs in your Xonotic")
    print("   data folder into the project. Existing files are never overwritten.\n")
    print("2) Change Revision:")
    print("   Renames the map files and the lightmap folder in maps/ and updates the")
    print(f"   .mapinfo title (format: {rev_str}). Shows a preview first.\n")
    print("3) Clean Backups:")
    print("   Lists and (after confirmation) deletes .bak / .autosave files in maps/.\n")
    print("4) Pack it:")
    print(f"   Builds a .pk3 from the project (prefix: {prefix_str}). Compiler leftovers,")
    print("   backups and working files (.prt, .srf, .xcf, ...) are left out. The")
    print("   maps/*.map source is included unless disabled in the settings.\n")
    print("Global Commands:")
    print("   h = help | s = settings | c = cancel / back | q = quit")
    print("=" * 75)


# ---------------------------------------------------------------------------
# MAIN PROGRAM LOOP
# ---------------------------------------------------------------------------
def list_projects():
    """Return the names of all folders in the projects folder that contain 'maps/'."""
    workspace = get_workspace_dir()
    if not workspace.is_dir():
        return []
    return sorted(
        p.name for p in workspace.iterdir()
        if p.is_dir() and (p / "maps").is_dir() and p.name not in IGNORE_DIRS
    )


def print_header():
    """Print banner + status note."""
    print("=" * 75)
    print(ASCII_BANNER)
    print(get_status_note())
    print("=" * 75)


def print_main_menu():
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


def validate_project_name(name):
    """Return an error message if 'name' is not a usable folder name, else None.

    Only letters, digits, '_' and '-' are allowed. Map names end up in file
    names, console commands and map lists, where spaces and special characters
    cause trouble.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        return "Use only letters, digits, '_' and '-' (no spaces or other characters)."
    if name in IGNORE_DIRS:
        return f"'{name}' is a reserved name."
    return None


def create_project():
    """Create a new map folder with the standard Xonotic sub-folders.

    Returns the new project's folder name (so the caller can open it right
    away), or None if nothing was created.
    """
    workspace = get_workspace_dir()
    if not workspace.is_dir():
        print(f"[ERROR] Projects folder '{workspace}' does not exist!")
        print("        Change it in the settings (press 's').")
        return None

    print("\n--- Create new map folder ---")
    print(f" - It will be created in: {workspace}")
    print(" - Allowed characters: letters, digits, '_' and '-'.")
    name = ask("> Enter new map folder name (c = cancel): ")
    if name.lower() in ("c", "x", "q", ""):
        print("[INFO] Cancelled.")
        return None

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

    try:
        project_dir.mkdir()
        for subdir in NEW_PROJECT_SUBDIRS:
            (project_dir / subdir).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[ERROR] Could not create the folder structure: {e}")
        return None

    print(f"\n[DONE] Created map folder: {project_dir}")
    for subdir in NEW_PROJECT_SUBDIRS:
        print(f"  [DIR] {name}/{subdir}/")
    return name


def choose_project():
    """Let the user pick an existing map folder by name or by list number.

    Returns the folder name, or None if the user went back to the main menu.
    """
    while True:
        workspace = get_workspace_dir()
        projects = list_projects()
        if projects:
            print("\nProjects found:")
            for i, name in enumerate(projects, start=1):
                print(f"  {i}) {name}")
        else:
            print(f"\n[INFO] No map folders found yet in '{workspace}'.")

        entry = ask("\n> Enter map directory name or number (c = back): ")
        lower = entry.lower()

        if lower == "q":
            sys.exit(0)
        elif lower == "h":
            show_help()
            continue
        elif lower == "s":
            settings_menu()          # the projects folder may have changed
            continue
        elif lower == "c":
            return None
        elif lower == "":
            continue

        # Only direct sub-folders are allowed - no paths like '../other'.
        if entry in (".", "..") or Path(entry).name != entry:
            print("[ERROR] Please enter just the folder name, not a path.")
            continue

        # An exact folder name always wins; otherwise treat digits as list number.
        if (workspace / entry).is_dir():
            return entry
        if entry.isdigit() and 1 <= int(entry) <= len(projects):
            return projects[int(entry) - 1]

        print(f"[ERROR] Project directory '{workspace / entry}' not found!")


def project_menu(map_name):
    """Action menu for one project. Returns when the user presses 'c'."""
    project_dir = get_workspace_dir() / map_name

    while True:
        print("\n" + "=" * 75)
        print(f"Active Project: {map_name}")
        print(get_status_note(project_dir))
        print("=" * 75)
        print("1) Export Textures")
        print("2) Change Revision")
        print("3) Clean Backups")
        print("4) Pack it")

        choice = ask("\n> Select option: ").lower()

        if choice == "1":
            export_textures(project_dir)
        elif choice == "2":
            change_revision(project_dir)
        elif choice == "3":
            clean_backups(project_dir)
        elif choice == "4":
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


def main():
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
