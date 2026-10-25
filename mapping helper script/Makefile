# =============================================================================
# XONOTIC MAPPING HELPER  (GNU Make edition)
# =============================================================================
#
# Port of mapping_helper.py. Same menus, same behaviour, no Python needed.
#
#   1) Export Assets   - scan the .map (brush faces, patches and entity keys
#                        like 'model' or 'noise') and your scripts/*.shader
#                        files, then copy everything the map uses - textures,
#                        shader scripts, sounds, models (with skins/materials
#                        and their textures): already in the project -> kept;
#                        in the wrong place -> moved (after confirmation);
#                        missing -> copied from the search paths (all .pk3
#                        files first, then loose files). Never overwrites.
#   2) Rename Map      - rename the map completely: map files, lightmap folder,
#                        .mapinfo title and project folder (preview + confirm).
#                        Prefixes/suffixes are not part of the map name, they
#                        only exist for the .pk3.
#   3) Pack it         - build a .pk3 with only the files a map needs (.map
#                        source optional). Only the PK3 name gets a revision;
#                        the files inside keep their names.
#
# REQUIREMENTS: GNU make, bash >= 4.4, unzip, zip OR bsdtar, GNU grep (-P), awk, find
#   Arch/CachyOS:  sudo pacman -S make unzip   (+ zip, or bsdtar which is usually there)
#
# USAGE (put this Makefile next to your map project folders):
#   make                       interactive menu (start menu -> project menu)
#   make assets MAP=Name       run one action directly (still interactive
#   make rename MAP=Name       where the original asks questions)
#   make pk3 MAP=Name
#   make new NAME=Name         create a new map folder (Xonotic layout)
#   make settings              settings menu
#   make help                  help screen
#
# SETTINGS are stored in 'mapping_helper.conf' next to this Makefile (Make
# syntax instead of JSON, so no extra tools are needed). Change them in the
# settings menu (press 's'). Keys: EXPORT_DIR, PK3_PREFIX, REV_PREFIX,
# XONOTIC_DIRS (search paths for assets, separated by ':', default ~/.xonotic),
# INCLUDE_MAP_SOURCE (yes/no), PROJECTS_DIR (where the script works).
#
# FILE LAYOUT (search for the banner of a section):
#   - settings and variables        defaults, mapping_helper.conf, MAP / NAME / KEY / VALUE
#   - define COMMON                 the shell helpers, grouped into labelled sections; they
#                                   are expanded into every recipe that needs them
#   - SMALL TARGETS                 banner, help, settings, get / set, check-map, new
#   - 1) EXPORT ASSETS              one shell function per phase, run in order at the end
#   - 2) RENAME MAP                 ask / plan / check / preview / perform / report
#   - 3) PACK IT                    packer, map name, revision suffix, archive
#   - MAIN PROGRAM LOOP             start menu and project menu
# =============================================================================

SHELL        := /bin/bash
.SHELLFLAGS  := -eu -o pipefail -c
.ONESHELL:
.SILENT:
.DEFAULT_GOAL := menu
MAKEFLAGS    += --no-print-directory

# Directory/path of this Makefile (taken before any include).
SELF   := $(abspath $(lastword $(MAKEFILE_LIST)))
MK_DIR := $(patsubst %/,%,$(dir $(SELF)))
CONF   := $(MK_DIR)/mapping_helper.conf

# ---- Settings (defaults; mapping_helper.conf and the command line override) --
EXPORT_DIR         ?=
PK3_PREFIX         ?=
REV_PREFIX         ?=
XONOTIC_DATA_DIR   ?=
XONOTIC_DIRS       ?=
INCLUDE_MAP_SOURCE ?= yes
PROJECTS_DIR       ?=
-include $(CONF)

# Effective projects folder: the setting, else the folder of this Makefile.
WORKSPACE   = $(or $(strip $(PROJECTS_DIR)),$(MK_DIR))
MAP        ?=
NAME       ?=
KEY        ?=
VALUE      ?=
PROJECT_DIR = $(WORKSPACE)/$(MAP)

.PHONY: menu banner help settings get set new check-map assets textures rename pk3

# =============================================================================
# SHARED SHELL HELPERS (expanded into every recipe)
# =============================================================================
define COMMON
# ---- DATA: folders, file formats, tool textures --------------------------------
NEW_SUBDIRS=(maps textures scripts sound models env gfx)
TOOL_TEXTURES=(common/caulk common/nodraw common/clip common/fullclip common/weapclip common/botclip common/trigger common/hint common/hintskip common/skip common/origin common/areaportal common/clusterportal common/donotenter common/nodrop common/noimpact common/nolightmap common/nonsolid common/structural)
MAP_SUFFIXES=("" _alpha _gloss _glow _glow_alpha _norm _norm_alpha _pants _shirt)
IMAGE_EXTS=(.png .tga .jpg .dds)
SOUND_EXTS=(.wav .ogg .flac)
MODEL_EXTS=(.md3 .iqm .obj .dpm .zym .psk .md2 .mdl)

# ---- CONSOLE HELPERS -----------------------------------------------------------
trim() { local s="$$1"; s="$${s#"$${s%%[![:space:]]*}"}"; s="$${s%"$${s##*[![:space:]]}"}"; printf '%s' "$$s"; }

rule() { printf '%*s\n' 75 '' | tr ' ' "$$1"; }

# ask <prompt>: result in ANS. EOF (Ctrl+D) quits cleanly.
ask() { ANS=""; if ! read -r -p "$$1" ANS; then echo; echo "Goodbye!"; exit 0; fi; ANS="$$(trim "$$ANS")"; }

# confirm <question>: anything except y/yes counts as no.
confirm() { ask "$$1 [y/N]: "; case "$${ANS,,}" in y|yes) return 0;; *) return 1;; esac; }

yesno() { case "$${1,,}" in yes|true|1) printf yes;; *) printf no;; esac; }

# ---- SETTINGS ACCESS (read through 'make get', write through 'make set') -------
# cfg <KEY>: read a fresh effective value (settings may change while running).
cfg() { $(MAKE) -s -f "$(SELF)" get KEY="$$1"; }

# setcfg <KEY> <VALUE>: store a setting in mapping_helper.conf.
setcfg() { $(MAKE) -s -f "$(SELF)" set KEY="$$1" VALUE="$$2" >/dev/null; }

# Search paths for assets, one per line: XONOTIC_DIRS (':' separated), else the folder of
# older versions (XONOTIC_DATA_DIR), else the Linux default ~/.xonotic.
xdirs() {
  local d="$(strip $(XONOTIC_DIRS))" old="$(strip $(XONOTIC_DATA_DIR))" p; local -a parts=()
  if [ -n "$$d" ]; then IFS=: read -r -a parts <<< "$$d"
  elif [ -n "$$old" ]; then parts=("$$old")
  else parts=("$$HOME/.xonotic"); fi
  for p in "$${parts[@]}"; do printf '%s\n' "$$p"; done
}

# Revision prefix: '_r', 'r' and ' r ' all become 'r'.
revprefix() { printf '%s' "$(REV_PREFIX)" | sed 's/^[[:space:]_]*//;s/[[:space:]]*$$//'; }

# ---- ASSET SOURCES (search paths, PK3s, loose files) ---------------------------
# Every .pk3 below the search paths (subfolders included: data/, dlcache, ...), one per
# line. 'Support' PK3s (name contains 'mapping' or 'extra') come first so the original
# game assets keep priority; otherwise the order of the search paths counts.
search_pk3s() {
  local r f n; local -a all=() sup=() oth=(); local -A seenp=()
  while IFS= read -r r; do
    if [ ! -d "$$r" ]; then continue; fi
    while IFS= read -r f; do
      if [ -z "$${seenp[$$f]+x}" ]; then seenp["$$f"]=1; all+=("$$f"); fi
    done < <(find -H "$$r" -xtype f -iname '*.pk3' | LC_ALL=C sort)
  done < <(xdirs)
  for f in "$${all[@]}"; do
    n="$${f##*/}"; n="$${n,,}"
    case "$$n" in *mapping*|*extra*) sup+=("$$f");; *) oth+=("$$f");; esac
  done
  for f in "$${sup[@]}"; do printf '%s\n' "$$f"; done
  for f in "$${oth[@]}"; do printf '%s\n' "$$f"; done
}

# Folders whose loose files the game reads like the content of a PK3: per search path its
# 'data' folder (as in ~/.xonotic/data/textures/custom/foo.png), or the path itself if it has
# none (an asset library with textures/, sound/, ... inside), plus every '*.pk3dir' folder.
# They are only searched after all PK3s.
loose_folders() {
  local r d; local -A seenf=()
  while IFS= read -r r; do
    if [ ! -d "$$r" ]; then continue; fi
    if [ -d "$$r/data" ]; then d="$$r/data"; else d="$$r"; fi
    if [ -z "$${seenf[$$d]+x}" ]; then seenf["$$d"]=1; printf '%s\n' "$$d"; fi
    while IFS= read -r d; do
      if [ -z "$${seenf[$$d]+x}" ]; then seenf["$$d"]=1; printf '%s\n' "$$d"; fi
    done < <(find -H "$$r" -type d -iname '*.pk3dir' | LC_ALL=C sort)
  done < <(xdirs)
}

# extract_to <pk3 or folder> <path inside> <destination file>
extract_to() { if [ -d "$$1" ]; then cp -- "$$1/$$2" "$$3"; else unzip -p "$$1" "$$2" > "$$3"; fi; }

# srclabel <pk3 or folder>: short name for messages.
srclabel() { if [ -d "$$1" ]; then printf '%s (folder)' "$${1##*/}"; else printf '%s' "$${1##*/}"; fi; }

# sound_slot <value>: where a sound belongs in the project: sound/<name> without extension.
sound_slot() {
  local v="$$1" bn ext="" base e; bn="$${v##*/}"; case "$$bn" in *.*) ext=".$${bn##*.}";; esac
  base="$$v"; for e in "$${SOUND_EXTS[@]}"; do if [ "$$e" = "$$ext" ]; then base="$${v%$$ext}"; fi; done
  case "$$base" in sound/*) ;; *) base="sound/$$base";; esac
  printf '%s' "$$base"
}

# ---- MAP FILES AND NAMES -------------------------------------------------------
# Real .map sources in a folder, newest first (autosaves ignored).
find_maps() { find "$$1" -maxdepth 1 -type f -name '*.map' ! -iname '*.autosave*' -printf '%T@ %f\n' | sort -rn | sed 's/^[^ ]* //'; }

# pick_map_file <maps_dir>: result in MAPFILE; returns 1 if none/cancelled.
pick_map_file() {
  local maps="$$1" c i choice; local -a cand=()
  while IFS= read -r c; do cand+=("$$c"); done < <(find_maps "$$maps")
  if [ "$${#cand[@]}" -eq 0 ]; then echo "[ERROR] No .map file found in '$$maps'!"; return 1; fi
  if [ "$${#cand[@]}" -eq 1 ]; then MAPFILE="$$maps/$${cand[0]}"; return 0; fi
  echo; echo "Multiple .map files found (newest first):"
  i=1; for c in "$${cand[@]}"; do echo "  $$i) $$c"; i=$$((i+1)); done
  ask "> Select file: "; choice="$${ANS,,}"
  case "$$choice" in
    c|x|q) echo "[INFO] Cancelled."; return 1;;
    "") MAPFILE="$$maps/$${cand[0]}"; return 0;;
  esac
  if [[ "$$choice" =~ ^[0-9]+$$ ]] && [ "$$choice" -ge 1 ] && [ "$$choice" -le "$${#cand[@]}" ]; then
    MAPFILE="$$maps/$${cand[$$((choice-1))]}"; return 0
  fi
  echo "[ERROR] Invalid selection."; return 1
}

# validate_name <name>: prints a message and returns 1 if unusable.
validate_name() {
  local n="$$1"
  case "$${n,,}" in c|h|q|s|x) echo "'$$n' is reserved for menu commands (h, s, c, q, x)."; return 1;; esac
  if ! [[ "$$n" =~ ^[A-Za-z0-9_-]+$$ ]]; then echo "Use only letters, digits, '_' and '-' (no spaces or other characters)."; return 1; fi
  case "$$n" in .git|.github|.idea|.vscode|__pycache__) echo "'$$n' is a reserved name."; return 1;; esac
  return 0
}

# starts_with_base <name> <base>: 'mymap_r2' matches 'mymap_r2.bsp' but NOT 'mymap_r20.bsp'.
starts_with_base() {
  local n="$$1" b="$$2" ch
  if [[ "$$n" != "$$b"* ]]; then return 1; fi
  if [ "$${#n}" -eq "$${#b}" ]; then return 0; fi
  ch="$${n:$${#b}:1}"
  if [[ "$$ch" =~ [[:alnum:]] ]]; then return 1; fi
  return 0
}

# ---- SHADER SCRIPTS AND MAPINFO ------------------------------------------------
# Shader script parser. Output lines: "D<TAB>name" (defined shader) and
# "R<TAB>shader<TAB>image" (image used by that shader via map/clampmap/animmap/skyparms).
parse_shader() {
  LC_ALL=C awk '
    function strip(x) { sub(/\.(png|tga|jpg|dds)$$/, "", x); return x }
    {
      line = $$0
      sub(/\/\/.*/, "", line)
      gsub(/^[ \t\r]+/, "", line); gsub(/[ \t\r]+$$/, "", line)
      if (line == "") next
      n = split(line, t, /[ \t]+/)
      if (depth == 0) {
        if (t[1] != "{" && t[1] != "}") { d = tolower(t[1]); gsub(/\\/, "/", d); cur = strip(d); print "D\t" cur }
      } else {
        key = tolower(t[1])
        if ((key == "map" || key == "clampmap") && n > 1) {
          if (substr(t[2], 1, 1) != "$$") print "R\t" cur "\t" strip(tolower(t[2]))
        } else if (key == "animmap") {
          for (i = 3; i <= n; i++) print "R\t" cur "\t" strip(tolower(t[i]))
        } else if (key == "skyparms" && n > 1 && t[2] != "-") {
          b = tolower(t[2]); split("_rt _lf _ft _bk _up _dn", s, " ")
          for (i = 1; i <= 6; i++) print "R\t" cur "\t" b s[i]
        }
      }
      o = gsub(/\{/, "{", line); c = gsub(/\}/, "}", line)
      depth += o - c; if (depth < 0) depth = 0
    }
  ' "$$1"
}

# update_mapinfo <file> <title>: set the first 'title' line (added if missing).
update_mapinfo() {
  local f="$$1" tmpf; tmpf="$$(mktemp)"
  LC_ALL=C awk -v nt="$$2" '
    BEGIN { found = 0 }
    {
      if (!found) {
        body = $$0; tail = ""
        if (match(body, /[ \t\r]*$$/)) { tail = substr(body, RSTART); body = substr(body, 1, RSTART - 1) }
        lb = tolower(body)
        if (match(lb, /^[ \t]*title[ \t]+/)) { found = 1; $$0 = substr(body, 1, RLENGTH) nt tail }
      }
      print
    }
    END { if (!found) print "title " nt }
  ' "$$f" > "$$tmpf"
  cat "$$tmpf" > "$$f"; rm -f "$$tmpf"
}

# check_extras <project dir> <map name as spelled> [search]: report things around the map that
# are easy to forget: the thumbnail shown in the map list (maps/<name>.jpg, also .png/.tga) and
# the music named by the .mapinfo 'cdtrack' line (sound/cdtracks/<track>). Only reports, never
# changes anything. With 'search' (inside Export Assets, which has the index arrays) music that
# is not in the project is also looked up in the search paths.
check_extras() {
  local pd="$$1" base="$$2" mode="$${3:-}" e found=0 hit=0 mi track lt slot expected
  for e in .jpg .png .tga; do
    if [ -n "$$(find "$$pd/maps" -maxdepth 1 -iname "$$base$$e" 2>/dev/null | head -n 1)" ]; then found=1; fi
  done
  if [ "$$found" -eq 0 ]; then
    echo "[WARNING] No thumbnail found: maps/$$base.jpg (also .png or .tga)."
    echo "          It is the picture shown in the map list of the game."
  fi
  mi="$$(find "$$pd/maps" -maxdepth 1 -iname "$$base.mapinfo" 2>/dev/null | head -n 1)"
  if [ -z "$$mi" ]; then
    echo "[WARNING] No maps/$$base.mapinfo found (title, description and game types come from it)."
    return 0
  fi
  track="$$(tr -d '\r' < "$$mi" | sed -E 's@//.*$$@@' | awk 'tolower($$1) == "cdtrack" && NF >= 2 { sub(/^[ \t]*[^ \t]+[ \t]+/, ""); sub(/[ \t]+$$/, ""); print; exit }')"
  if [ -z "$$track" ]; then return 0; fi
  case "$$track" in *[!0-9]*) ;; *) return 0;; esac        # a plain number is a CD track
  lt="$${track,,}"; slot="$$(sound_slot "cdtracks/$$lt")"; expected="sound/cdtracks/$$track"
  for e in "$${SOUND_EXTS[@]}"; do
    if [ -n "$$(find "$$pd" -ipath "$$pd/$$slot$$e" 2>/dev/null | head -n 1)" ]; then hit=1; fi
  done
  if [ "$$hit" -eq 1 ]; then
    echo "[INFO] Music from the .mapinfo (cdtrack): $$expected is in your project."
  elif [ "$$mode" != search ]; then
    echo "[WARNING] Music from the .mapinfo (cdtrack) is not in your project: $$expected"
    echo "          Fine if it ships with the game, otherwise players hear no music."
  else
    find_key "cdtracks/$$lt" sound
    if [ -n "$$FKEY" ]; then
      echo "[INFO] Music from the .mapinfo (cdtrack) is not in your project, but exists in the search paths ($$(srclabel "$${IDXP[$$FKEY]}")): $${IDXN[$$FKEY]}"
      echo "       It is not copied - add it yourself if it is your own music."
    else
      echo "[WARNING] Music from the .mapinfo (cdtrack) was not found in your project or the search paths: $$expected"
      echo "          Fine if it ships with the game, otherwise players hear no music."
    fi
  fi
}

# ---- PACKING RULES AND REVISION SUFFIXES ---------------------------------------
# Editor backups: '*.bak', '*.autosave', '*.autosave.map', ...
is_backup() { local l="$${1,,}"; case "$$l" in *.bak|*.autosave*) return 0;; *) return 1;; esac; }

# should_pack <relative path>: needs include_src=yes|no to be set.
should_pack() {
  local rel="$$1" name tmpn ext="" d; local -a parts
  name="$${rel##*/}"
  if [[ "$$rel" == */* ]]; then
    IFS=/ read -ra parts <<< "$${rel%/*}"
    for d in "$${parts[@]}"; do
      case "$$d" in .git|.github|.idea|.vscode|__pycache__) return 1;; esac
    done
  fi
  case "$$name" in .DS_Store|Thumbs.db|.gitignore|mapping_helper.py|mapping_helper_config.json|mapping_helper.conf|Makefile) return 1;; esac
  if is_backup "$$name"; then return 1; fi
  tmpn="$${name#.}"
  case "$$tmpn" in *.*) ext=".$${tmpn##*.}"; ext="$${ext,,}";; esac
  case "$$ext" in .pk3|.bak|.prt|.srf|.log|.lin|.tmp|.xcf|.psd|.blend|.blend1|.fcstd|.fcstd1) return 1;; esac
  if [ "$$ext" = ".map" ]; then
    if [ "$$include_src" = yes ] && [ "$${rel%%/*}" = maps ]; then return 0; fi
    return 1
  fi
  return 0
}

# split_revision <stem> <prefix>: sets CORE and OLDREV ('mymap_r3' -> 'mymap' + '_r3').
split_revision() {
  local stem="$$1" rp="$$2" m="" re
  CORE="$$stem"; OLDREV=""
  shopt -s nocasematch
  re="_$${rp}[0-9]+[a-z]*$$"
  if [[ "$$stem" =~ $$re ]]; then m="$${BASH_REMATCH[0]}"
  else
    re="_[a-z]*[0-9]+[a-z]*$$"
    if [[ "$$stem" =~ $$re ]]; then m="$${BASH_REMATCH[0]}"; fi
  fi
  shopt -u nocasematch
  if [ -n "$$m" ]; then CORE="$${stem:0:$${#stem}-$${#m}}"; OLDREV="$$m"; fi
}

# prompt_suffix <prompt> <rev_prefix> [default number]: result in SUFFIX as '_<word><number>';
# returns 1 if cancelled/invalid. A number alone gets the word from the settings ('7' -> '_r7');
# anything starting with a letter is used as typed ('v2' -> '_v2', '_alpha3' -> '_alpha3').
prompt_suffix() {
  local t
  ask "$$1"; t="$${ANS,,}"; t="$$(printf '%s' "$$t" | sed 's/^_*//')"
  if [ -z "$$t" ] && [ "$$#" -ge 3 ]; then SUFFIX="_$$2$$3"; return 0; fi
  case "$$t" in c|x|q|"") return 1;; esac
  case "$$t" in h|s) echo "[ERROR] '$$t' is a menu command, not a suffix. Nothing was changed."; return 1;; esac
  if ! [[ "$$t" =~ ^[a-z0-9]+$$ ]]; then echo "[ERROR] The suffix may only contain letters and digits."; return 1; fi
  if [[ "$$t" =~ ^[0-9] ]]; then SUFFIX="_$$2$$t"; else SUFFIX="_$$t"; fi
  return 0
}

# ---- MENUS AND HELP ------------------------------------------------------------
# Three-line status footer shown above every menu ($1 = optional project dir).
status_note() {
  local ed pf rv src dir_str ps rs
  ed="$$(cfg EXPORT_DIR)"; pf="$$(cfg PK3_PREFIX)"; rv="$$(cfg REV_PREFIX)"; src="$$(yesno "$$(cfg INCLUDE_MAP_SOURCE)")"
  if [ -n "$$ed" ]; then dir_str="$$ed"; elif [ -n "$${1-}" ]; then dir_str="$$1"; else dir_str="[Map Folder (Default)]"; fi
  if [ -n "$$pf" ]; then ps="'$$pf'"; else ps="None"; fi
  if [ -n "$$rv" ]; then rs="'$$rv'"; else rs="None"; fi
  echo "  Note: h=help, s=settings, c=cancel, q=quit"
  echo "  Export Path: $$dir_str"
  echo "  Prefix: $$ps | Rev: $$rs | .map in pk3: $$src"
}

show_help() {
  local pf rv ps rs
  pf="$$(cfg PK3_PREFIX)"; rv="$$(cfg REV_PREFIX)"
  if [ -n "$$pf" ]; then ps="'$$pf'"; else ps="None"; fi
  if [ -n "$$rv" ]; then rs="'$$rv'"; else rs="None"; fi
  echo; rule "="
  echo "                      HELP MENU"
  rule "="
  echo "Placement & Execution:"
  echo "   Put this Makefile next to your map project folders and run:"
  echo "      make"
  echo
  echo "Start Menu:"
  echo "   1) Choose map folder    - pick an existing project by name or number."
  echo "   2) Create new map folder - creates the folder with the standard Xonotic"
  echo "      layout (maps, textures, scripts, sound, models, env, gfx)."
  echo "   Projects are listed and created in the 'Projects Folder' (settings,"
  echo "   default: the folder this Makefile lives in)."
  echo
  echo "1) Export Assets:"
  echo "   Scans the .map (brush faces, patches and entity keys like 'model' and"
  echo "   'noise') and your scripts/*.shader files and makes sure the project has"
  echo "   everything the map uses. For every asset:"
  echo "     - already in the project at the expected place: kept as it is"
  echo "     - in the project, but at a wrong place: moved there (you confirm)"
  echo "     - missing: copied from the search paths (settings, option 4) - first"
  echo "       from all .pk3 files below them (support PKs first), then from loose"
  echo "       files (data/ folder, *.pk3dir folders)"
  echo "   Assets: textures (incl. _glow/_norm/_gloss companions and skybox faces),"
  echo "   the shader scripts defining them, sounds, and models with their skins,"
  echo "   materials and textures. Existing files are never overwritten."
  echo "   At the end it also reports a missing thumbnail (maps/<name>.jpg) and"
  echo "   whether the music named by 'cdtrack' in the .mapinfo is in the project."
  echo
  echo "2) Rename Map:"
  echo "   Renames the map completely: files and lightmap folder in maps/, the"
  echo "   .mapinfo title and the project folder. Shows a preview first. Prefixes"
  echo "   and suffixes are not part of the map name - they only exist for the"
  echo "   .pk3 (settings 2 and 3)."
  echo
  echo "3) Pack it:"
  echo "   Builds a .pk3 from the project (prefix: $$ps). Compiler leftovers,"
  echo "   backups and working files (.prt, .srf, .xcf, ...) are left out. The"
  echo "   maps/*.map source is included unless disabled in the settings."
  echo "   Before packing it warns about a missing thumbnail (maps/<name>.jpg) and"
  echo "   about music from the .mapinfo ('cdtrack') that is not in the project."
  echo "   If the map name or an earlier .pk3 already has a revision suffix, you can"
  echo "   keep it, raise it by 1, enter your own or remove it. Otherwise you are"
  echo "   asked whether the .pk3 name should get one. Your own suffix: a number"
  echo "   gets the word from the settings (2 -> _r2), anything starting with a"
  echo "   letter is used as typed (v2 -> _v2). The map files inside the package"
  echo "   keep their names."
  echo
  echo "Global Commands:"
  echo "   h = help | s = settings | c = cancel / back | q = quit"
  rule "="
}

# cur_dirs: the current search paths, one per line (fresh from the settings).
cur_dirs() {
  local d old; d="$$(cfg XONOTIC_DIRS)"
  if [ -n "$$d" ]; then printf '%s\n' "$$d" | tr ':' '\n'
  else
    old="$$(cfg XONOTIC_DATA_DIR)"
    if [ -n "$$old" ]; then printf '%s\n' "$$old"; else printf '%s\n' "$$HOME/.xonotic"; fi
  fi
}

search_paths_menu() {
  local c v np i joined idx p dup; local -a shown
  while true; do
    mapfile -t shown < <(cur_dirs)
    echo; echo "--- Search Paths for Xonotic assets ---"
    echo " - Missing assets are taken from these folders: first from all .pk3 files"
    echo "   below them, then from loose files (the data/ folder, *.pk3dir folders)."
    echo " - The first match wins; the order of the list is the priority."
    for i in "$${!shown[@]}"; do echo "  $$((i+1))) $${shown[$$i]}"; done
    echo "  a) Add a path"
    echo "  r) Remove a path"
    echo "  d) Reset to default"
    ask "> Select option: "; c="$${ANS,,}"
    case "$$c" in
      a)
        ask "> Enter path: "; v="$$ANS"
        case "$${v,,}" in c|x|q|"") continue;; esac
        np="$$(realpath -m -- "$${v/#\~/$$HOME}")"
        if [ ! -d "$$np" ]; then echo "[ERROR] '$$np' does not exist or is not a folder!"; continue; fi
        case "$$np" in *:*) echo "[ERROR] Paths containing ':' are not supported."; continue;; esac
        dup=0; for p in "$${shown[@]}"; do if [ "$$p" = "$$np" ]; then dup=1; fi; done
        if [ "$$dup" -eq 1 ]; then echo "[INFO] That path is already in the list."; continue; fi
        shown+=("$$np"); joined="$$(IFS=:; printf '%s' "$${shown[*]}")"
        setcfg XONOTIC_DIRS "$$joined"; echo "[SUCCESS] Path added: $$np" ;;
      r)
        ask "> Enter number: "; v="$$ANS"
        case "$${v,,}" in c|x|q|"") continue;; esac
        if ! [[ "$$v" =~ ^[0-9]+$$ ]] || [ "$$v" -lt 1 ] || [ "$$v" -gt "$${#shown[@]}" ]; then echo "[ERROR] Invalid number!"; continue; fi
        idx=$$((v-1)); np="$${shown[$$idx]}"; unset "shown[$$idx]"; shown=("$${shown[@]}")
        if [ "$${#shown[@]}" -eq 0 ]; then setcfg XONOTIC_DIRS ""; else joined="$$(IFS=:; printf '%s' "$${shown[*]}")"; setcfg XONOTIC_DIRS "$$joined"; fi
        setcfg XONOTIC_DATA_DIR ""
        echo "[SUCCESS] Path removed: $$np" ;;
      d)
        setcfg XONOTIC_DIRS ""; setcfg XONOTIC_DATA_DIR ""
        echo "[SUCCESS] Search paths reset to the default ($$HOME/.xonotic)." ;;
      c|x|q|"") return 0 ;;
      *) echo "[ERROR] Invalid option!" ;;
    esac
  done
}

settings_menu() {
  local ed pf rv dd src pd choice value np bad x; local -a sdirs
  while true; do
    ed="$$(cfg EXPORT_DIR)"; pf="$$(cfg PK3_PREFIX)"; rv="$$(cfg REV_PREFIX)"
    dd="$$(cfg XONOTIC_DIRS)$$(cfg XONOTIC_DATA_DIR)"; src="$$(yesno "$$(cfg INCLUDE_MAP_SOURCE)")"; pd="$$(cfg PROJECTS_DIR)"
    echo; rule "="
    echo "                  SETTINGS MENU"
    status_note
    rule "="
    echo "1) PK3 Export Path:      $${ed:-[Not set - saves inside map folder]}"
    if [ -n "$$pf" ]; then echo "2) PK3 Filename Prefix:  '$$pf'"; else echo "2) PK3 Filename Prefix:  [Not set - None]"; fi
    if [ -n "$$rv" ]; then echo "3) Revision Format:      '$$rv'"; else echo "3) Revision Format:      [Not set - None]"; fi
    if [ -n "$$dd" ]; then
      mapfile -t sdirs < <(cur_dirs)
      echo "4) Search Paths:         $${sdirs[0]}"
      for x in "$${sdirs[@]:1}"; do echo "                         $$x"; done
    else echo "4) Search Paths:         [Default: $$HOME/.xonotic]"; fi
    echo "5) Include .map in PK3:  $$src"
    if [ -n "$$pd" ]; then echo "6) Projects Folder:      $$pd"; else echo "6) Projects Folder:      [Default: $(MK_DIR)]"; fi
    rule "-"
    echo; ask "> Select option: "; choice="$${ANS,,}"
    case "$$choice" in
      1)
        echo; echo "--- Set PK3 Export Path ---"
        echo " - Enter an absolute path to save packed PK3s there automatically."
        echo " - Type 'default' or press Enter to reset to default."
        ask "> Enter path: "; value="$$ANS"
        case "$${value,,}" in c|x|q) continue;; esac
        if [ -z "$$value" ] || [ "$${value,,}" = default ]; then
          setcfg EXPORT_DIR ""; echo "[SUCCESS] Export directory reset to default."
        else
          np="$$(realpath -m -- "$${value/#\~/$$HOME}")"
          if [ ! -d "$$np" ]; then echo "[ERROR] '$$np' does not exist or is not a folder!"
          else setcfg EXPORT_DIR "$$np"; echo "[SUCCESS] Custom export directory saved: $$np"; fi
        fi ;;
      2)
        echo; echo "--- Set PK3 Filename Prefix ---"
        echo " - Enter a prefix for generated PK3 files (e.g. 'duke_')."
        echo " - Press Enter without typing anything to remove the prefix."
        ask "> Enter prefix: "; value="$$ANS"
        case "$${value,,}" in c|x|q) continue;; esac
        bad=0
        case "$$value" in *'/'*|*'\'*|*':'*|*'*'*|*'?'*|*'"'*|*'<'*|*'>'*|*'|'*) bad=1;; esac
        if [ "$$bad" -eq 1 ]; then echo "[ERROR] The prefix contains characters that are not allowed in file names."; continue; fi
        setcfg PK3_PREFIX "$$value"; echo "[SUCCESS] PK3 prefix updated to: '$$value'" ;;
      3)
        echo; echo "--- Set Revision Format ---"
        echo " - Enter the word placed before a revision number in the PK3 name,"
        echo "   e.g. 'r' gives mymap_r3, 'v' gives mymap_v3, 'alpha' gives mymap_alpha3."
        echo " - Press Enter without typing anything to use plain numbers (mymap_3)."
        ask "> Enter revision prefix: "; value="$$(printf '%s' "$$ANS" | sed 's/^[[:space:]_]*//;s/[[:space:]]*$$//')"
        case "$${value,,}" in c|x|q) continue;; esac
        if ! [[ "$$value" =~ ^[A-Za-z]*$$ ]]; then echo "[ERROR] Only letters are allowed (an underscore is added automatically)."; continue; fi
        setcfg REV_PREFIX "$$value"; echo "[SUCCESS] Revision format updated to: '$$value'" ;;
      4) search_paths_menu ;;
      5)
        if [ "$$src" = yes ]; then setcfg INCLUDE_MAP_SOURCE no; echo "[SUCCESS] The .map source will be left out of the PK3."
        else setcfg INCLUDE_MAP_SOURCE yes; echo "[SUCCESS] The .map source will be included in the PK3."; fi ;;
      6)
        echo; echo "--- Set Projects Folder ---"
        echo " - Folder in which your map folders are listed and new ones are created."
        echo " - Type 'default' or press Enter to use the folder of this Makefile."
        ask "> Enter path: "; value="$$ANS"
        case "$${value,,}" in c|x|q) continue;; esac
        if [ -z "$$value" ] || [ "$${value,,}" = default ]; then
          setcfg PROJECTS_DIR ""; echo "[SUCCESS] Projects folder reset to the Makefile's folder."
        else
          np="$$(realpath -m -- "$${value/#\~/$$HOME}")"
          if [ ! -d "$$np" ]; then
            if ! confirm "'$$np' does not exist. Create it?"; then continue; fi
            if ! mkdir -p "$$np"; then echo "[ERROR] Could not create folder"; continue; fi
          fi
          setcfg PROJECTS_DIR "$$np"; echo "[SUCCESS] Projects folder saved: $$np"
        fi ;;
      h) show_help ;;
      c|q|"") break ;;
      *) echo "[ERROR] Invalid option!" ;;
    esac
  done
}
endef

# =============================================================================
# SMALL TARGETS
# =============================================================================
banner:
	echo
	sed 's/^~//' <<'EOF'
	~ __  __                   _               _   _      _
	~|  \/  | __ _ _ __  _ __ (_)_ __   __ _  | | | | ___| |_ __   ___ _ __
	~| |\/| |/ _` | '_ \| '_ \| | '_ \ / _` | | |_| |/ _ \ | '_ \ / _ \ '__|
	~| |  | | (_| | |_) | |_) | | | | | (_| | |  _  |  __/ | |_) |  __/ |
	~|_|  |_|\__,_| .__/| .__/|_|_| |_|\__, | |_| |_|\___|_| .__/ \___|_|
	~             |_|   |_|            |___/               |_|
	EOF

help:
	$(COMMON)
	show_help

settings:
	$(COMMON)
	settings_menu

# Print one effective setting (used by the menus to read fresh values).
get:
	$(COMMON)
	case "$(KEY)" in
	  WORKSPACE) printf '%s' "$(WORKSPACE)";;
		  EXPORT_DIR|PK3_PREFIX|REV_PREFIX|XONOTIC_DATA_DIR|XONOTIC_DIRS|PROJECTS_DIR|INCLUDE_MAP_SOURCE) printf '%s' "$($(KEY))";;
	esac

# Store a setting in mapping_helper.conf (an empty VALUE resets it).
set:
	case "$(KEY)" in EXPORT_DIR|PK3_PREFIX|REV_PREFIX|XONOTIC_DATA_DIR|XONOTIC_DIRS|PROJECTS_DIR|INCLUDE_MAP_SOURCE) ;; *) echo "[ERROR] Unknown setting '$(KEY)'" >&2; exit 1;; esac
	touch "$(CONF)"
	grep -v -E '^$(KEY)[[:space:]]*[:?]?=' "$(CONF)" > "$(CONF).tmp" || true
	printf '%s = %s\n' '$(KEY)' '$(VALUE)' >> "$(CONF).tmp"
	mv "$(CONF).tmp" "$(CONF)"

check-map:
	if [ -z "$(MAP)" ]; then echo "[ERROR] No map given. Use MAP=<folder name> or run 'make' for the menu." >&2; exit 1; fi
	if [ ! -d "$(PROJECT_DIR)" ]; then echo "[ERROR] Project directory '$(PROJECT_DIR)' not found!" >&2; exit 1; fi

# Create a new map folder with the standard Xonotic layout (make new NAME=Foo).
new:
	$(COMMON)
	name="$(NAME)"
	if [ -z "$$name" ]; then ask "> Enter new map folder name: "; name="$$ANS"; fi
	case "$${name,,}" in c|x|"") echo "[INFO] Cancelled."; exit 0;; esac
	if ! err="$$(validate_name "$$name")"; then echo "[ERROR] $$err"; exit 1; fi
	pdir="$(WORKSPACE)/$$name"
	if [ -e "$$pdir" ]; then echo "[ERROR] '$$pdir' already exists - nothing was changed."; exit 1; fi
	mkdir "$$pdir"
	for s in "$${NEW_SUBDIRS[@]}"; do mkdir -p "$$pdir/$$s"; done
	echo; echo "[DONE] Created map folder: $$pdir"
	for s in "$${NEW_SUBDIRS[@]}"; do echo "  [DIR] $$name/$$s/"; done

# =============================================================================
# 1) EXPORT ASSETS
# =============================================================================
textures: assets

assets: check-map
	$(COMMON)
	maps_dir="$(PROJECT_DIR)/maps"
	if [ ! -d "$$maps_dir" ]; then echo "[ERROR] Subfolder '$$maps_dir' does not exist!"; exit 1; fi
	pick_map_file "$$maps_dir" || exit 0
	map_file="$$MAPFILE"
	echo; echo "[INFO] Analyzing map file: $${map_file##*/}..."
	tmp="$$(mktemp -d)"; trap 'rm -rf "$$tmp"' EXIT
	printf '%s\n' "$${TOOL_TEXTURES[@]}" > "$$tmp/tools"

	# ---- Helpers on the indexes (used by several phases) ------------------------------
	# Shared state of the helpers below: the counters, the result of the last copy
	# (CSTATUS), the last lookup (FKEY) and further files found in a model (EXTRA).
	COPIED=0; SKIPPED=0; CSTATUS=""; FKEY=""; EXTRA=()
	# has_local <base> <extensions...>: does the project have base + one of the extensions?
	has_local() { local b="$$1" e; shift; for e in "$$@"; do if [ -n "$${LOC[$$b$$e]+x}" ]; then return 0; fi; done; return 1; }
	copy_key() {
	  local k="$$1" pk real target rt
	  pk="$${IDXP[$$k]}"; real="$${IDXN[$$k]}"
	  target="$$PD/$$real"; rt="$$(realpath -m -- "$$target")"
	  case "$$rt" in "$$ROOT"/*) ;; *) CSTATUS=blocked; return 0;; esac
	  if [ -e "$$target" ]; then SKIPPED=$$((SKIPPED+1)); CSTATUS=exists; return 0; fi
	  mkdir -p "$$(dirname "$$target")"
	  extract_to "$$pk" "$$real" "$$target"
	  COPIED=$$((COPIED+1)); CSTATUS=copied
	  echo "  [+] Copied ($$(srclabel "$$pk")): $$real"
	}
	# has_key <key> [local]: is the key in the project (local) or in the search paths?
	has_key() { if [ "$${2:-}" = local ]; then [ -n "$${LOC[$$1]+x}" ]; else [ -n "$${IDXP[$$1]+x}" ]; fi; }
	# find_key <value> sound|model [local]: first matching key in FKEY (empty if none).
	find_key() {
	  local v="$$1" kind="$$2" where="$${3:-}" bn ext="" base e n prefix known=0
	  local -a exts=() prefixes=() names=()
	  if [ "$$kind" = sound ]; then exts=("$${SOUND_EXTS[@]}"); prefixes=("sound/" ""); else exts=("$${MODEL_EXTS[@]}"); prefixes=(""); fi
	  FKEY=""
	  bn="$${v##*/}"; case "$$bn" in *.*) ext=".$${bn##*.}";; esac
	  base="$${v%$$ext}"
	  for e in "$${exts[@]}"; do if [ "$$e" = "$$ext" ]; then known=1; fi; done
	  if [ "$$known" -eq 1 ]; then
	    names=("$$v"); for e in "$${exts[@]}"; do if [ "$$e" != "$$ext" ]; then names+=("$$base$$e"); fi; done
	  else
	    for e in "$${exts[@]}"; do names+=("$$v$$e"); done
	  fi
	  for prefix in "$${prefixes[@]}"; do
	    for n in "$${names[@]}"; do
	      if has_key "$$prefix$$n" "$$where"; then FKEY="$$prefix$$n"; return 0; fi
	    done
	  done
	}
	# Files that belong to a model by name: skins, framegroups, materials (from the key file $2).
	pathstem() { local bn="$${1##*/}"; if [[ "$$1" == */* ]]; then printf '%s/%s' "$${1%/*}" "$${bn%.*}"; else printf '%s' "$${bn%.*}"; fi; }
	companions() {
	  local mk="$$1" kf="$$2" stem k rest; stem="$$(pathstem "$$mk")"
	  { grep -F -- "$$stem" "$$kf" || true; } | while IFS= read -r k; do
	    if [ "$$k" = "$$mk" ]; then continue; fi
	    case "$$k" in "$$stem"*) ;; *) continue;; esac
	    rest="$${k#"$$stem"}"
	    if [[ "$$rest" =~ ^(_[a-z0-9]+)?(\.[a-z0-9]+)?\.(skin|framegroups|mtl)$$ ]]; then printf '%s\n' "$$k"; fi
	  done
	}
	# scan_model <file on disk> <key>: texture names go to modeltex, further files (as 'L|key'
	# for the project, 'S|key' for the search paths) to EXTRA.
	scan_model() {
	  local path="$$1" key="$$2" bn ext="" mdir="" n
	  EXTRA=()
	  bn="$${key##*/}"; case "$$bn" in *.*) ext=".$${bn##*.}";; esac
	  if [[ "$$key" == */* ]]; then mdir="$${key%/*}"; fi
	  if [ ! -r "$$path" ]; then return 0; fi
	  case "$$ext" in
	    .md3|.iqm|.dpm|.zym|.psk|.md2|.mdl)
	      # Texture names are stored as plain text strings inside the file.
	      { grep -a -o -E '[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+' "$$path" || true; } | tr 'A-Z' 'a-z' | { grep -v -E '\.(md3|iqm|obj|dpm|zym|psk|md2|mdl|wav|ogg|flac)$$' || true; } | sed -E 's/\.(png|tga|jpg|dds)$$//' >> "$$tmp/modeltex" ;;
	    .skin)
	      # 'meshname,texture/path'
	      awk -F',' 'NF >= 2 { v = $$0; sub(/^[^,]*,/, "", v); gsub(/^[ \t]+/, "", v); gsub(/[ \t\r]+$$/, "", v); gsub(/\\/, "/", v); if (v != "") print tolower(v) }' "$$path" | sed -E 's/\.(png|tga|jpg|dds)$$//' >> "$$tmp/modeltex" ;;
	    .mtl)
	      tr -d '\r' < "$$path" | awk 'tolower($$1) ~ /^(map_|bump|disp|decal|refl)/ && NF >= 2 { print $$NF }' | while IFS= read -r n; do
	        n="$${n//\\//}"; n="$${n,,}"; n="$${n#/}"
	        case "$$n" in textures/*|models/*|gfx/*|env/*|sound/*) ;; *) if [ -n "$$mdir" ]; then n="$$mdir/$$n"; fi;; esac
	        printf '%s\n' "$$n"
	      done | sed -E 's/\.(png|tga|jpg|dds)$$//' >> "$$tmp/modeltex" ;;
	    .obj)
	      while IFS= read -r n; do
	        n="$${n//\\//}"; n="$${n,,}"
	        if [ -n "$$mdir" ]; then n="$$mdir/$$n"; fi
	        if [ -n "$${LOC[$$n]+x}" ]; then EXTRA+=("L|$$n"); elif [ -n "$${IDXP[$$n]+x}" ]; then EXTRA+=("S|$$n"); fi
	      done < <(tr -d '\r' < "$$path" | sed -n -E 's/^[mM][tT][lL][lL][iI][bB][[:space:]]+(.*[^[:space:]])[[:space:]]*$$/\1/p') ;;
	  esac
	}

	# ---- The phases, in the order they run --------------------------------------------

	# --- 1a) Brush textures (classic + brush primitives) and patches
	#         ('patchDef2/3' + '{' + a line holding the texture).
	scan_brush_textures() {
	  {
	    grep -oP '^\s*\(\s*[^)]+\)\s*\(\s*[^)]+\)\s*\(\s*[^)]+\)\s*(?:\(\s*\(\s*[^)]*\)\s*\(\s*[^)]*\)\s*\)\s*)?\K("[^"]+"|\S+)' "$$map_file" || true
	    LC_ALL=C awk '
	      expect { s = $$0; gsub(/^[ \t\r]+/, "", s); gsub(/[ \t\r]+$$/, "", s); if (s == "" || s == "{") next; expect = 0; print s; next }
	      { s = tolower($$0); gsub(/^[ \t\r]+/, "", s); if (s ~ /^patchdef[23]/) expect = 1 }
	    ' "$$map_file"
	  } | tr 'A-Z' 'a-z' | tr '\\' '/' | tr -d '"' | sed -E 's/\.(png|tga|jpg|dds)$$//' | grep -v -E '^$$|^\(|^\)|^noshader' | grep -v -x -F -f "$$tmp/tools" | awk '{ if (index($$0, "textures/") == 1) print; else print "textures/" $$0 }' | LC_ALL=C sort -u > "$$tmp/brush" || true
	}

	# --- 1b) Entity assets: '"key" "value"' lines. Sounds, models and sky/image names.
	#         Absolute paths ('/home/me/map/sound/x.ogg') are cut down to 'sound/x.ogg' and reported.
	scan_entity_assets() {
	  awk -F'"' 'NF >= 5 && $$1 ~ /^[ \t]*$$/ { print tolower($$2) "\t" $$4 }' "$$map_file" > "$$tmp/pairs"
	  awk -F'"' 'NF >= 5 && $$1 ~ /^[ \t]*$$/ { print $$4 }' "$$map_file" > "$$tmp/origvals"
	  paste "$$tmp/pairs" "$$tmp/origvals" > "$$tmp/pairs2"
	  LC_ALL=C awk -F'\t' '
	    function rfind(s, t,   p, last, off) { last = 0; off = 0; while ((p = index(substr(s, off + 1), t)) > 0) { last = off + p; off = last } return last }
	    BEGIN {
	      n = split("noise noise1 noise2 sound", a, " "); for (i = 1; i <= n; i++) snd[a[i]] = 1
	      n = split("model model2", a, " "); for (i = 1; i <= n; i++) mdl[a[i]] = 1
	      n = split("skybox skyname sky", a, " "); for (i = 1; i <= n; i++) sky[a[i]] = 1
	      nr = split("textures models gfx env sound", rootn, " ")
	    }
	    {
	      k = $$1; v = tolower($$2); orig = $$3; gsub(/\\/, "/", v)
	      gsub(/^[ \t]+/, "", v); gsub(/[ \t\r]+$$/, "", v); gsub(/^[ \t]+/, "", orig); gsub(/[ \t\r]+$$/, "", orig)
	      abs = 0
	      if (substr(v, 1, 1) == "/" || v ~ /^[a-z]:\//) {
	        abs = 1; best = 0
	        for (r = 1; r <= nr; r++) { p = rfind(v, "/" rootn[r] "/"); if (p > best) best = p }
	        if (best > 0) v = substr(v, best + 1)
	      }
	      sub(/^\/+/, "", v)
	      if (v == "" || substr(v, 1, 1) == "*") next
	      ext = ""; if (match(v, /\.[a-z0-9]+$$/)) ext = substr(v, RSTART)
	      cat = ""
	      if (k in snd) cat = "S"
	      else if (k in mdl) cat = "M"
	      else if (k in sky) { cat = "T"; sub(/\.(png|tga|jpg|dds)$$/, "", v) }
	      else if (v !~ / / && index(v, "/") > 0) {
	        if (ext ~ /^\.(wav|ogg|flac)$$/) cat = "S"
	        else if (ext ~ /^\.(md3|iqm|obj|dpm|zym|psk|md2|mdl)$$/) cat = "M"
	        else if (ext ~ /^\.(png|tga|jpg|dds)$$/) { cat = "T"; sub(/\.(png|tga|jpg|dds)$$/, "", v) }
	      }
	      if (cat != "") { print cat "\t" v; if (abs) print "W\t" k "\t" orig "\t" v }
	    }
	  ' "$$tmp/pairs2" | LC_ALL=C sort -u > "$$tmp/ent"
	  awk -F'\t' '$$1 == "S" { print $$2 }' "$$tmp/ent" > "$$tmp/sounds"
	  awk -F'\t' '$$1 == "M" { print $$2 }' "$$tmp/ent" > "$$tmp/models"
	  awk -F'\t' '$$1 == "T" { print $$2 }' "$$tmp/ent" > "$$tmp/enttex"
	  echo "[SUCCESS] Found $$(wc -l < "$$tmp/brush") unique textures, $$(wc -l < "$$tmp/sounds") sound(s) and $$(wc -l < "$$tmp/models") model(s) in the .map file."
	  while IFS=$$'\t' read -r _ wk orig fixed; do
	    hint="$$fixed"; case "$$wk" in noise|noise1|noise2|sound) hint="$${fixed#sound/}";; esac
	    echo "[WARNING] Absolute path in the map: \"$$wk\" \"$$orig\""
	    echo "          That only works on your computer. Change the value to \"$$hint\" in NetRadiant."
	  done < <(awk -F'\t' '$$1 == "W"' "$$tmp/ent")
	}

	# --- 2) Own shaders of this project (what they define and reference).
	parse_own_shaders() {
	  : > "$$tmp/defined"; : > "$$tmp/ownrows"
	  shopt -s nullglob
	  for sf in "$(PROJECT_DIR)/scripts"/*.shader; do
	    parse_shader "$$sf" > "$$tmp/p"
	    awk -F'\t' '$$1 == "D" { print $$2 }' "$$tmp/p" | LC_ALL=C sort -u > "$$tmp/pd"
	    awk -F'\t' '$$1 == "R" { print $$3 }' "$$tmp/p" | LC_ALL=C sort -u > "$$tmp/pr"
	    cat "$$tmp/pd" >> "$$tmp/defined"; cat "$$tmp/p" >> "$$tmp/ownrows"
	    echo "[INFO] Parsed shader script: $${sf##*/} ($$(wc -l < "$$tmp/pd") shaders, $$(wc -l < "$$tmp/pr") image references)"
	  done
	  LC_ALL=C sort -u "$$tmp/defined" -o "$$tmp/defined"
	}

	# --- 3) Where can we get assets from? Search paths: all .pk3 first, then loose files.
	index_sources() {
	  mapfile -t pks < <(search_pk3s)
	  mapfile -t lfs < <(loose_folders)
	  where="$$(xdirs | paste -sd, - | sed 's/,/, /g')"
	  if [ "$${#pks[@]}" -eq 0 ] && [ "$${#lfs[@]}" -eq 0 ]; then
	    echo "[ERROR] No PK3s or data folders found in: $$where"
	    echo "        Set the correct search paths in the settings menu (press 's')."
	    exit 1
	  fi
	  if [ "$${#pks[@]}" -le 10 ]; then
	    names=""; for p in "$${pks[@]}"; do names="$$names$${names:+, }'$${p##*/}'"; done
	    echo "[INFO] Scanning $${#pks[@]} archive(s): [$$names]"
	  else
	    echo "[INFO] Scanning $${#pks[@]} archives in $$where (this can take a moment)..."
	  fi
	  if [ "$${#lfs[@]}" -gt 0 ]; then
	    names=""; for p in "$${lfs[@]}"; do names="$$names$${names:+, }'$$p'"; done
	    echo "[INFO] Then loose files in $${#lfs[@]} folder(s): [$$names]"
	  fi
	  : > "$$tmp/index.raw"
	  for p in "$${pks[@]}"; do
	    if ! unzip -Z1 "$$p" 2>/dev/null | LC_ALL=C awk -v pk="$$p" '!/\/$$/ { print tolower($$0) "\t" pk "\t" $$0 }' >> "$$tmp/index.raw"; then
	      echo "[WARNING] Skipping unreadable archive $${p##*/}"
	    fi
	  done
	  : > "$$tmp/index.loose"
	  for f in "$${lfs[@]}"; do
	    find -H "$$f" -xtype f ! -iname '*.pk3' -printf '%P\n' | LC_ALL=C awk -v d="$$f" 'tolower($$0) !~ /\.pk3dir\// { print tolower($$0) "\t" d "\t" $$0 }' >> "$$tmp/index.loose"
	  done
	  # PK3s first, loose files only as fallback: the first entry of a path wins.
	  cat "$$tmp/index.raw" "$$tmp/index.loose" | awk -F'\t' '!seen[$$1]++' > "$$tmp/index"
	  PD="$(PROJECT_DIR)"; ROOT="$$(realpath "$$PD")"
	  # What the project already has (files made by you or exported earlier).
	  find "$$PD" -xtype f -printf '%P\n' | LC_ALL=C awk '{ print tolower($$0) "\tLOCAL\t" $$0 }' > "$$tmp/index.local"
	  declare -gA IDXP=() IDXN=() LOC=()
	  while IFS=$$'\t' read -r k p n; do IDXP["$$k"]="$$p"; IDXN["$$k"]="$$n"; done < "$$tmp/index"
	  while IFS=$$'\t' read -r k p n; do LOC["$$k"]="$$n"; done < "$$tmp/index.local"
	  cut -f1 "$$tmp/index" | LC_ALL=C sort > "$$tmp/keys.search"
	  cut -f1 "$$tmp/index.local" | LC_ALL=C sort > "$$tmp/keys.local"
	}

	# --- 4) Models: the project first, then the search paths. Models can name textures
	#         themselves (inside the model, in .skin / .mtl files); those are handled like map
	#         textures below.
	process_models() {
	  : > "$$tmp/missing_sounds"; : > "$$tmp/missing_models"; : > "$$tmp/modeltex"
	  declare -gA SEEN=(); MPRESENT=0
	  while IFS= read -r v; do
	    if [ -z "$$v" ]; then continue; fi
	    src=L; find_key "$$v" model local
	    if [ -z "$$FKEY" ]; then src=S; find_key "$$v" model; fi
	    if [ -z "$$FKEY" ]; then echo "$$v" >> "$$tmp/missing_models"; continue; fi
	    # Companions come from the same side as the model itself.
	    if [ "$$src" = L ]; then MPRESENT=$$((MPRESENT+1)); kf="$$tmp/keys.local"; else kf="$$tmp/keys.search"; fi
	    queue=("$$src|$$FKEY")
	    while IFS= read -r c; do queue+=("$$src|$$c"); done < <(companions "$$FKEY" "$$kf")
	    pos=0
	    while [ "$$pos" -lt "$${#queue[@]}" ]; do        # the queue can grow (.obj -> .mtl)
	      item="$${queue[$$pos]}"; pos=$$((pos+1))
	      if [ -n "$${SEEN[$$item]+x}" ]; then continue; fi
	      SEEN["$$item"]=1
	      kind="$${item%%|*}"; key="$${item#*|}"
	      if [ "$$kind" = S ]; then
	        copy_key "$$key"
	        if [ "$$CSTATUS" = blocked ]; then continue; fi
	        mpath="$$PD/$${IDXN[$$key]}"
	      else
	        mpath="$$PD/$${LOC[$$key]}"
	      fi
	      scan_model "$$mpath" "$$key"
	      if [ "$${#EXTRA[@]}" -gt 0 ]; then queue+=("$${EXTRA[@]}"); fi
	    done
	  done < "$$tmp/models"
	}

	# --- 5) All texture/shader names in play: brush, entity (sky, images) and model textures.
	collect_texture_names() {
	  cat "$$tmp/brush" "$$tmp/enttex" "$$tmp/modeltex" | { grep -v -E '^$$|^[.]' || true; } | LC_ALL=C sort -u > "$$tmp/texnames"
	  grep -x -F -f "$$tmp/defined" "$$tmp/texnames" > "$$tmp/custom" || true
	  ncustom="$$(wc -l < "$$tmp/custom")"
	  if [ "$$ncustom" -gt 0 ]; then echo "[INFO] $$ncustom texture name(s) are your own shaders (images are taken from the shader files instead)."; fi
	  # Only the shaders the map really uses count, so unused shaders in a big script do not pull in extra images.
	  awk -F'\t' 'NR == FNR { want[$$0] = 1; next } $$1 == "R" && ($$2 in want) { print $$3 }' "$$tmp/custom" "$$tmp/ownrows" | LC_ALL=C sort -u > "$$tmp/refs"
	  grep -v -x -F -f "$$tmp/defined" "$$tmp/texnames" > "$$tmp/b2" || true
	}

	# --- 6) Is it already in the project? If a file sits at a wrong place, offer to move it
	#         where the map expects it. Slots: 'I<TAB>texture base' and 'S<TAB>sound base'.
	correct_misplaced() {
	  { sed 's/^/I\t/' "$$tmp/b2"; sed 's/^/I\t/' "$$tmp/refs"; while IFS= read -r v; do if [ -n "$$v" ]; then printf 'S\t%s\n' "$$(sound_slot "$$v")"; fi; done < "$$tmp/sounds"; } | { grep -v -P '^[IS]\t$$' || true; } | LC_ALL=C sort -u > "$$tmp/slots"
	  cut -f2 "$$tmp/slots" > "$$tmp/slots.bases"
	  : > "$$tmp/slots.missing"
	  while IFS=$$'\t' read -r cl b; do
	    if [ "$$cl" = I ]; then
	      if has_local "$$b" "$${IMAGE_EXTS[@]}"; then continue; fi
	    else
	      if has_local "$$b" "$${SOUND_EXTS[@]}"; then continue; fi
	    fi
	    printf '%s\t%s\n' "$$cl" "$$b" >> "$$tmp/slots.missing"
	  done < "$$tmp/slots"
	  # A project file counts as the misplaced asset if its name is the same and it is the only
	  # such file. Files that sit correctly for another asset, and maps/ (lightmaps), are never touched.
	  LC_ALL=C awk -F'\t' '
	    function stem(p,   n, a, b) { n = split(p, a, "/"); b = a[n]; sub(/\.[a-z0-9]+$$/, "", b); return b }
	    function extof(p) { if (match(p, /\.[a-z0-9]+$$/)) return substr(p, RSTART); return "" }
	    function noext(p) { sub(/\.[a-z0-9]+$$/, "", p); return p }
	    FILENAME == ARGV[1] { cls[$$2] = $$1; miss[$$2] = 1; st = stem($$2); nb[st]++; sb[st, nb[st]] = $$2; next }
	    FILENAME == ARGV[2] { allb[$$1] = 1; next }
	    {
	      k = $$1; real = $$3
	      if (k ~ /^maps\//) next
	      st = stem(k); if (!(st in nb)) next
	      if (noext(k) in allb) next
	      e = extof(k)
	      for (i = 1; i <= nb[st]; i++) {
	        b = sb[st, i]
	        if (cls[b] == "I" && e !~ /^\.(png|tga|jpg|dds)$$/) continue
	        if (cls[b] == "S" && e !~ /^\.(wav|ogg|flac)$$/) continue
	        cnt[b]++; cand[b] = real; lst[b] = lst[b] (cnt[b] > 1 ? ", " : "") real
	      }
	    }
	    END { for (b in miss) { if (cnt[b] == 1) print "U\t" b "\t" cand[b]; else if (cnt[b] > 1) print "A\t" b "\t" lst[b] } }
	  ' "$$tmp/slots.missing" "$$tmp/slots.bases" "$$tmp/index.local" | LC_ALL=C sort > "$$tmp/misplaced"
	  # Plan the moves; companion maps (_norm, _gloss, ...) next to a misplaced texture move with it.
	  : > "$$tmp/moves"
	  while IFS=$$'\t' read -r tag b real; do
	    if [ "$$tag" != U ]; then continue; fi
	    bn="$${real##*/}"; ext=""; case "$$bn" in *.*) ext=".$${bn##*.}";; esac; ext="$${ext,,}"
	    printf '%s\t%s\n' "$$real" "$$b$$ext" >> "$$tmp/moves"
	    case "$$b" in sound/*) continue;; esac
	    folder=""; if [[ "$$real" == */* ]]; then folder="$${real%/*}"; fi
	    stem="$${bn%.*}"
	    for suf in "$${MAP_SUFFIXES[@]}"; do
	      if [ -z "$$suf" ]; then continue; fi
	      for e in "$${IMAGE_EXTS[@]}"; do
	        ck="$$folder/$$stem$$suf$$e"; ck="$${ck#/}"; ck="$${ck,,}"; dst="$$b$$suf$$e"
	        if [ -n "$${LOC[$$ck]+x}" ] && [ -z "$${LOC[$$dst]+x}" ]; then printf '%s\t%s\n' "$${LOC[$$ck]}" "$$dst" >> "$$tmp/moves"; fi
	      done
	    done
	  done < "$$tmp/misplaced"
	  moved=0
	  if [ -s "$$tmp/moves" ]; then
	    echo; echo "[INFO] These assets are in your project, but not where the map expects them:"
	    while IFS=$$'\t' read -r a b; do echo "  $$a  ->  $$b"; done < "$$tmp/moves"
	    echo
	    if confirm "> Move them to the expected place?"; then
	      while IFS=$$'\t' read -r a b; do
	        case "$$b" in *..*) continue;; esac
	        if [ ! -e "$$PD/$$a" ] || [ -e "$$PD/$$b" ]; then continue; fi
	        mkdir -p "$$(dirname "$$PD/$$b")"; mv -- "$$PD/$$a" "$$PD/$$b"
	        echo "  [FIX] Moved: $$a  ->  $$b"; moved=$$((moved+1))
	        ka="$${a,,}"; kb="$${b,,}"; unset "LOC[$$ka]"; LOC["$$kb"]="$$b"
	      done < "$$tmp/moves"
	    else
	      echo "[INFO] Left as they are. Missing assets are taken from the search paths."
	    fi
	  fi
	  while IFS=$$'\t' read -r tag b lst; do
	    if [ "$$tag" = A ]; then echo "[INFO] More than one file could be '$$b', nothing moved: $$lst"; fi
	  done < "$$tmp/misplaced"
	  # What is still missing in the project after the corrections.
	  : > "$$tmp/b2m"; : > "$$tmp/refsm"
	  while IFS= read -r n; do if [ -n "$$n" ] && ! has_local "$$n" "$${IMAGE_EXTS[@]}"; then echo "$$n" >> "$$tmp/b2m"; fi; done < "$$tmp/b2"
	  while IFS= read -r n; do if [ -n "$$n" ] && ! has_local "$$n" "$${IMAGE_EXTS[@]}"; then echo "$$n" >> "$$tmp/refsm"; fi; done < "$$tmp/refs"
	  TEXPRESENT=$$(( $$(wc -l < "$$tmp/b2") + $$(wc -l < "$$tmp/refs") - $$(wc -l < "$$tmp/b2m") - $$(wc -l < "$$tmp/refsm") ))
	}

	# --- 7) Sounds the project does not have yet.
	copy_missing_sounds() {
	  SPRESENT=0
	  while IFS= read -r v; do
	    if [ -z "$$v" ]; then continue; fi
	    if has_local "$$(sound_slot "$$v")" "$${SOUND_EXTS[@]}"; then SPRESENT=$$((SPRESENT+1)); continue; fi
	    find_key "$$v" sound
	    if [ -z "$$FKEY" ]; then echo "$$v" >> "$$tmp/missing_sounds"; continue; fi
	    copy_key "$$FKEY"
	  done < "$$tmp/sounds"
	}

	# --- 8) Texture names that are shaders defined inside a PK3 (sprites, alpha, sky, ...):
	#         the shader script is copied to scripts/ and the images that shader uses are exported.
	provide_pk3_shaders() {
	  : > "$$tmp/provided"; : > "$$tmp/pk3refs"; : > "$$tmp/shfiles"
	  declare -gA PROV=()
	  if [ -s "$$tmp/b2m" ]; then
	    mkdir -p "$$tmp/sh"; n=0
	    while IFS=$$'\t' read -r k pk real; do
	      n=$$((n+1))
	      extract_to "$$pk" "$$real" "$$tmp/sh/$$n.shader" 2>/dev/null || continue
	      if ! grep -q -i -F -f "$$tmp/b2m" "$$tmp/sh/$$n.shader"; then rm -f "$$tmp/sh/$$n.shader"; continue; fi
	      parse_shader "$$tmp/sh/$$n.shader" > "$$tmp/pp"
	      while IFS= read -r nm; do
	        if [ -z "$${PROV[$$nm]+x}" ] && grep -q -x -F -- "$$nm" "$$tmp/b2m"; then
	          PROV["$$nm"]=1
	          echo "$$nm" >> "$$tmp/provided"
	          awk -F'\t' -v n="$$nm" '$$1 == "R" && $$2 == n { print $$3 }' "$$tmp/pp" >> "$$tmp/pk3refs"
	          printf '%s\t%s\t%s\n' "$$pk" "$$real" "$$nm" >> "$$tmp/shfiles"
	        fi
	      done < <(awk -F'\t' '$$1 == "D" { print $$2 }' "$$tmp/pp")
	      rm -f "$$tmp/sh/$$n.shader"
	    done < <(awk -F'\t' '$$1 ~ /^scripts\/.*\.shader$$/' "$$tmp/index")
	  fi
	  grep -v -x -F -f "$$tmp/provided" "$$tmp/b2m" > "$$tmp/b3" || true
	  nprov="$$(wc -l < "$$tmp/provided")"
	  nsh="$$(cut -f1,2 "$$tmp/shfiles" | LC_ALL=C sort -u | wc -l)"
	  if [ "$$nprov" -gt 0 ]; then echo "[INFO] $$nprov texture name(s) are defined by shaders in PK3s ($$nsh shader script(s) will be copied to scripts/)."; fi
	  # Everything we should try to find as an image file.
	  cat "$$tmp/b3" "$$tmp/refsm" "$$tmp/pk3refs" | LC_ALL=C sort -u > "$$tmp/needed"
	}

	# --- 9) Shader scripts first (never overwritten, never outside the project), then the images.
	copy_shaders_and_images() {
	  shcopied=0; missing=()
	  while IFS=$$'\t' read -r pk real; do
	    names="$$(awk -F'\t' -v p="$$pk" -v r="$$real" '$$1 == p && $$2 == r { print $$3 }' "$$tmp/shfiles" | paste -sd, - | sed 's/,/, /g')"
	    target="$$PD/$$real"
	    rt="$$(realpath -m -- "$$target")"
	    case "$$rt" in "$$ROOT"/*) ;; *) continue;; esac
	    if [ -e "$$target" ]; then
	      echo "  [!] Shader script already exists, not overwritten: $$real"
	      echo "      It does not define: $$names"
	      continue
	    fi
	    mkdir -p "$$(dirname "$$target")"
	    extract_to "$$pk" "$$real" "$$target"
	    echo "  [+] Copied shader ($$(srclabel "$$pk")): $$real  (defines: $$names)"
	    shcopied=$$((shcopied+1))
	  done < <(cut -f1,2 "$$tmp/shfiles" | awk -F'\t' '!seen[$$1 FS $$2]++' | LC_ALL=C sort -s -t$$'\t' -k2,2)
	  while IFS= read -r base; do
	    if [ -z "$$base" ]; then continue; fi
	    if has_local "$$base" "$${IMAGE_EXTS[@]}"; then TEXPRESENT=$$((TEXPRESENT+1)); continue; fi
	    found=0
	    # Try the plain texture plus every companion map, in every format.
	    for suf in "$${MAP_SUFFIXES[@]}"; do
	      for ext in "$${IMAGE_EXTS[@]}"; do
	        key="$$base$$suf$$ext"
	        if [ -n "$${IDXP[$$key]+x}" ]; then found=1; copy_key "$$key"; fi
	      done
	    done
	    if [ "$$found" -eq 0 ]; then missing+=("$$base"); fi
	  done < "$$tmp/needed"
	}

	# --- 10) Report.
	report_results() {
	  ALREADY=$$((TEXPRESENT + SPRESENT + MPRESENT))
	  if [ "$$ALREADY" -gt 0 ]; then
	    echo; echo "[INFO] $$ALREADY asset(s) were already in your project and were left as they are."
	  fi
	  if [ "$${#missing[@]}" -gt 0 ] || [ -s "$$tmp/missing_sounds" ] || [ -s "$$tmp/missing_models" ]; then
	    # For every name that was not found: files with the same name at another path.
	    find "$$PD" -xtype f -printf '%P\n' | LC_ALL=C awk '{ print tolower($$0) "\tLOCAL\t" $$0 }' > "$$tmp/index.local"
	    cat "$$tmp/index" "$$tmp/index.local" > "$$tmp/index.hint"
	    { printf '%s\n' "$${missing[@]}"; cat "$$tmp/missing_sounds" "$$tmp/missing_models"; } | { grep -v '^$$' || true; } | while IFS= read -r nm; do s="$${nm##*/}"; printf '%s\n' "$${s%.*}"; done > "$$tmp/stems"
	    LC_ALL=C awk -F'\t' 'NR == FNR { want[$$0] = 1; next } { n = split($$1, a, "/"); b = a[n]; sub(/\.[a-z0-9]+$$/, "", b); if (b in want) print b "\t" $$3 "\t" $$2 }' "$$tmp/stems" "$$tmp/index.hint" > "$$tmp/hints"
	    show_missing() {
	      local nm="$$1" st real pk src
	      echo "    [?] $$nm"
	      st="$${nm##*/}"; st="$${st%.*}"
	      awk -F'\t' -v s="$$st" '$$1 == s' "$$tmp/hints" | head -n 3 | while IFS=$$'\t' read -r _ real pk; do
	        if [ "$$pk" = LOCAL ]; then src="your project"; else src="$$(srclabel "$$pk")"; fi
	        echo "        similar: $$real  ($$src)"
	      done
	    }
	    echo; echo "[INFO] Not found in your project or in the search paths:"
	    if [ "$${#missing[@]}" -gt 0 ]; then echo "  textures:"; for m in "$${missing[@]}"; do show_missing "$$m"; done; fi
	    if [ -s "$$tmp/missing_sounds" ]; then echo "  sounds:"; while IFS= read -r m; do show_missing "$$m"; done < "$$tmp/missing_sounds"; fi
	    if [ -s "$$tmp/missing_models" ]; then echo "  models:"; while IFS= read -r m; do show_missing "$$m"; done < "$$tmp/missing_models"; fi
	    echo "      These are usually shipped with the base game (players already have"
	    echo "      them) or defined by a shader. 'similar' shows a file with the same"
	    echo "      name at another path, a common cause of 'not found'."
	  fi
	}

	# --- 11) Thumbnail and music: only reported, never changed.
	report_map_extras() {
	  map_name="$${map_file##*/}"; map_name="$${map_name%.map}"
	  echo
	  check_extras "$$PD" "$$map_name" search
	}

	# --- 12) The closing summary.
	print_summary() {
	  movedtext=""; if [ "$$moved" -gt 0 ]; then movedtext=", moved $$moved to the expected place"; fi
	  echo; echo "[DONE] Copied $$COPIED file(s) and $$shcopied shader script(s)$$movedtext, skipped $$SKIPPED that already exist."
	  echo "[NOTE] Shader scripts are copied as a whole file, so they may also contain"
	  echo "       shaders you do not use. Only images of the shaders your map uses"
	  echo "       are exported."
	}

	# ---- Run -------------------------------------------------------------------------
	scan_brush_textures
	scan_entity_assets
	parse_own_shaders
	index_sources
	process_models
	collect_texture_names
	correct_misplaced
	copy_missing_sounds
	provide_pk3_shaders
	copy_shaders_and_images
	report_results
	report_map_extras
	print_summary


# =============================================================================
# 2) RENAME MAP
# =============================================================================
rename: check-map
	$(COMMON)
	maps_dir="$(PROJECT_DIR)/maps"
	pdir="$(PROJECT_DIR)"

	# Ask for the new name (result in new_base). Cancelling, a bad name or the
	# current name ends the recipe.
	ask_new_name() {
	  ask "> Enter new map name: "; new_base="$$ANS"
	  case "$${new_base,,}" in c|x|q|"") echo "[INFO] Renaming cancelled."; exit 0;; esac
	  # Same rules as for new map folders (letters, digits, '_' and '-').
	  err="$$(validate_name "$$new_base" || true)"
	  if [ -n "$$err" ]; then echo "[ERROR] $$err"; exit 1; fi
	  if [ "$$new_base" = "$$current_base" ]; then echo "[INFO] That is already the current name. Nothing to do."; exit 0; fi
	}

	# Everything that belongs to the current name, as paths relative to the project folder:
	# in maps/ the files + lightmap folder, in gfx/ the minimap (<name>_mini.tga).
	plan_renames() {
	  SRC=(); DST=()
	  for sub in maps gfx; do
	    if [ ! -d "$$pdir/$$sub" ]; then continue; fi
	    while IFS= read -r e; do
	      if starts_with_base "$$e" "$$current_base"; then SRC+=("$$sub/$$e"); DST+=("$$sub/$$new_base$${e:$${#current_base}}"); fi
	    done < <(find "$$pdir/$$sub" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)
	  done

	  # The project folder follows the map name.
	  new_folder=""
	  if [ "$(MAP)" != "$$new_base" ]; then new_folder="$(WORKSPACE)/$$new_base"; fi
	}

	# Refuse to run if a target already exists (and is not itself being renamed).
	check_clashes() {
	  clashes=()
	  for d in "$${DST[@]}"; do
	    if [ -e "$$pdir/$$d" ]; then
	      insrc=0; for s in "$${SRC[@]}"; do if [ "$$s" = "$$d" ]; then insrc=1; fi; done
	      if [ "$$insrc" -eq 0 ]; then clashes+=("$$d"); fi
	    fi
	  done
	  if [ -n "$$new_folder" ] && [ -e "$$new_folder" ]; then clashes+=("$$new_base  (project folder)"); fi
	  if [ "$${#clashes[@]}" -gt 0 ]; then
	    echo "[ERROR] These targets already exist, nothing was changed:"
	    for d in "$${clashes[@]}"; do echo "  - $$d"; done
	    exit 1
	  fi
	}

	# Show everything the rename is going to do, before asking to proceed.
	show_preview() {
	  echo; echo "The following renames will be performed:"
	  for i in "$${!SRC[@]}"; do
	    if [ -d "$$pdir/$${SRC[$$i]}" ]; then kind="DIR "; else kind="FILE"; fi
	    echo "  [$$kind] $${SRC[$$i]}  ->  $${DST[$$i]}"
	  done
	  if [ -n "$$new_folder" ]; then echo "  [DIR ] project folder: $(MAP)  ->  $$new_base"; fi
	  echo "  [INFO] The title in '$$new_base.mapinfo' will be set to '$$new_base'."
	  # Hint against a doubled prefix in the .pk3 name (the packer adds its own).
	  pf="$(strip $(PK3_PREFIX))"
	  if [ -n "$$pf" ] && [[ "$${new_base,,}" == "$${pf,,}"* ]]; then
	    echo "  [NOTE] The name already starts with your PK3 prefix '$$pf'. That prefix is added automatically when packing,"
	    echo "         so the .pk3 would be called '$$pf$$new_base.pk3'."
	  fi
	}

	# Do the renames (files first, project folder last) and set the .mapinfo title.
	# Stop at the first error so the state stays understandable.
	perform_renames() {
	  for i in "$${!SRC[@]}"; do
	    if ! mv -- "$$pdir/$${SRC[$$i]}" "$$pdir/$${DST[$$i]}"; then
	      echo "[ERROR] Could not rename '$${SRC[$$i]}'"
	      echo "        Stopped. Some files may already have been renamed."
	      exit 1
	    fi
	  done
	  root="$$pdir"; renamed=""
	  if [ -n "$$new_folder" ]; then
	    if mv -- "$$pdir" "$$new_folder"; then root="$$new_folder"; renamed="$$new_base"
	    else echo "[ERROR] Could not rename the project folder"; echo "        The map files were renamed, the folder keeps its old name."; fi
	  fi
	  if [ -f "$$root/maps/$$new_base.mapinfo" ]; then
	    update_mapinfo "$$root/maps/$$new_base.mapinfo" "$$new_base"
	    echo "  [INFO] Updated the .mapinfo title to '$$new_base'."
	  else
	    echo "  [INFO] No .mapinfo found for this map - title not updated."
	  fi
	  echo; echo "[DONE] Map renamed: $$current_base  ->  $$new_base"
	}

	# Things that may still carry the old name; not touched on purpose because
	# other files (shaders, the .map itself) refer to them by name.
	report_leftovers() {
	  leftovers=()
	  shopt -s nullglob
	  for e in "$$root/textures"/*/; do
	    n="$${e%/}"; n="$${n##*/}"
	    if [ "$${n,,}" = "$${current_base,,}" ]; then leftovers+=("textures/$$n/"); fi
	  done
	  for e in "$$root/scripts"/*; do
	    n="$${e##*/}"
	    if [ -f "$$e" ] && [[ "$${n,,}" == *"$${current_base,,}"* ]]; then leftovers+=("scripts/$$n"); fi
	  done
	  if [ "$${#leftovers[@]}" -gt 0 ]; then
	    echo "  [NOTE] These still use the old name and were NOT renamed (shaders and"
	    echo "         the .map refer to them by name):"
	    for e in "$${leftovers[@]}"; do echo "    - $$e"; done
	  fi
	}

	# ---- Run -----------------------------------------------------------------------
	if [ ! -d "$$maps_dir" ]; then echo "[ERROR] Directory '$$maps_dir' does not exist!"; exit 1; fi
	pick_map_file "$$maps_dir" || exit 0
	current_base="$${MAPFILE##*/}"; current_base="$${current_base%.map}"
	echo; echo "[INFO] Current map name: $$current_base"
	ask_new_name
	plan_renames
	check_clashes
	show_preview
	echo
	if ! confirm "> Proceed?"; then echo "[INFO] Renaming cancelled. Nothing was changed."; exit 0; fi

	perform_renames
	report_leftovers
	# Tell the menu about the new project folder name.
	if [ -n "$$renamed" ] && [ -n "$${RENAME_OUT:-}" ]; then echo "$$renamed" > "$$RENAME_OUT"; fi

# =============================================================================
# 3) PACK IT
# =============================================================================
pk3: check-map
	$(COMMON)
	pd="$(PROJECT_DIR)"; maps_dir="$$pd/maps"; project_name="$(MAP)"
	include_src="$$(yesno "$(strip $(INCLUDE_MAP_SOURCE))")"
	# Target folder and file name: prefix + name (+ revision).
	prefix="$(strip $(PK3_PREFIX))"
	rev_prefix="$$(revprefix)"
	custom="$(strip $(EXPORT_DIR))"
	if [ -n "$$custom" ]; then export_dir="$$custom"; else export_dir="$$pd"; fi

	# Choose the tool that writes the archive (result in packer).
	# Packer: Info-ZIP 'zip' if installed, else bsdtar (libarchive). Both write Deflate.
	pick_packer() {
	  if command -v zip >/dev/null; then packer=zip
	  elif command -v bsdtar >/dev/null; then packer=bsdtar
	  else echo "[ERROR] Neither 'zip' nor 'bsdtar' found (sudo pacman -S zip)"; exit 1; fi
	}

	# Work out the map name for the file name (map_base, shown_name).
	# Map name for the file name: prefer the compiled .bsp (newest).
	detect_map_name() {
	  map_base="$${project_name,,}"; shown_name="$$project_name"
	  bsps=()
	  if [ -d "$$maps_dir" ]; then
	    while IFS= read -r b; do bsps+=("$$b"); done < <(find "$$maps_dir" -maxdepth 1 -type f -name '*.bsp' -printf '%T@ %f\n' | sort -rn | sed 's/^[^ ]* //')
	  fi
	  if [ "$${#bsps[@]}" -gt 0 ]; then
	    b="$${bsps[0]%.bsp}"; map_base="$${b,,}"; shown_name="$$b"
	    if [ "$${#bsps[@]}" -gt 1 ]; then echo "[WARNING] Several .bsp files found; using the newest: $${bsps[0]}"; fi
	  else
	    src1=""
	    if [ -d "$$maps_dir" ]; then src1="$$(find_maps "$$maps_dir" | head -n 1)"; fi
	    if [ -n "$$src1" ]; then b="$${src1%.map}"; map_base="$${b,,}"; shown_name="$$b"; fi
	    echo "[WARNING] No compiled .bsp found in maps/ - the package would not be playable."
	    if ! confirm "> Pack anyway?"; then echo "[INFO] Packing cancelled."; exit 0; fi
	  fi
	}

	# Decide the revision suffix of the PK3 name (the files inside keep their names). If a revision
	# is already known - the map files carry one ('mymap_r5') or earlier packages exist in the
	# export folder - you are not asked whether to add one: you can keep it, raise it by 1, enter
	# your own or remove it. Without a known revision you are asked whether to add one.
	choose_rev() {
	  local core name_rev lhead f n ln rest num cur k choice word source mt
	  local -A EX=() EXW=()
	  # If the map files carry a revision ('mymap_r2'), the PK3 name is built from the plain name.
	  split_revision "$$map_base" "$$rev_prefix"
	  core="$$CORE"; name_rev="$$OLDREV"
	  lhead="$$prefix$$core"; lhead="$${lhead,,}_"
	  shopt -s nullglob
	  if [ -d "$$export_dir" ]; then
	    for f in "$$export_dir"/*.pk3; do
	      n="$${f##*/}"; ln="$${n,,}"
	      if [[ "$$ln" == "$$lhead"* ]]; then
	        rest="$${ln#"$$lhead"}"
	        if [[ "$$rest" =~ ^([a-z]*)([0-9]+)\.pk3$$ ]]; then
	          num=$$((10#$${BASH_REMATCH[2]})); word="$${BASH_REMATCH[1]}"
	          # one number with several words: the word from the settings wins
	          if [ -z "$${EX[$$num]+x}" ] || [ "$$word" = "$${rev_prefix,,}" ]; then EX[$$num]="$$n"; EXW[$$num]="$$word"; fi
	        fi
	      fi
	    done
	  fi
	  if [ -n "$$name_rev" ]; then
	    echo; echo "[INFO] The map files are named '$$map_base' (suffix '$$name_rev'). The files inside stay unchanged; the PK3 name uses '$$core'."
	    mt="$${name_rev,,}"
	    if [[ "$$mt" =~ ^_([a-z]*)([0-9]+)[a-z]*$$ ]]; then
	      num=$$((10#$${BASH_REMATCH[2]})); word="$${BASH_REMATCH[1]}"
	      if [ -z "$${EX[$$num]+x}" ]; then EX[$$num]="map file name '$$map_base'"; EXW[$$num]="$$word"; fi
	    fi
	  fi
	  if [ "$${#EX[@]}" -eq 0 ]; then
	    # Nothing known yet: ask whether the PK3 should get a suffix at all.
	    echo
	    if ! confirm "> Add a revision number to the PK3 file name?"; then PK3_BASE="$$core"; REVISION=""; return 0; fi
	    if ! prompt_suffix "> Enter suffix: " "$$rev_prefix" "1"; then return 1; fi
	    PK3_BASE="$$core"; REVISION="$$SUFFIX"; return 0
	  fi
	  cur=-1; for k in "$${!EX[@]}"; do if [ "$$k" -gt "$$cur" ]; then cur="$$k"; fi; done
	  word="$${EXW[$$cur]}"
	  echo "[INFO] Current revision: _$$word$$cur  (found: $${EX[$$cur]})"
	  echo "  1) Keep current   ->  _$$word$$cur"
	  echo "  2) Increase by 1  ->  _$$word$$((cur+1))"
	  echo "  3) Enter my own"
	  echo "  4) Remove it      ->  no suffix"
	  ask "> Select option: "; choice="$${ANS,,}"
	  case "$$choice" in
	    c|x|q) return 1;;
	    1) REVISION="_$$word$$cur";;
	    ""|2) REVISION="_$$word$$((cur+1))";;
	    3) if ! prompt_suffix "> Enter suffix: " "$$rev_prefix"; then return 1; fi; REVISION="$$SUFFIX";;
	    4) REVISION="";;
	    *) echo "[ERROR] Invalid selection."; return 1;;
	  esac
	  PK3_BASE="$$core"
	}

	# Build the output path (output_path) and ask before replacing an existing file.
	prepare_target() {
	  output_name="$$prefix$$PK3_BASE$$REVISION.pk3"

	  mkdir -p "$$export_dir"
	  export_dir="$$(realpath "$$export_dir")"
	  output_path="$$export_dir/$$output_name"
	  if [ -e "$$output_path" ]; then
	    echo
	    if ! confirm "> '$$output_name' already exists. Overwrite?"; then echo "[INFO] Packing cancelled. Nothing was changed."; exit 0; fi
	  fi
	}

	# List the files to pack (sorted, filtered by the packing rules) into $tmp/files.
	# File list (sorted), filtered by the packing rules.
	list_pack_files() {
	  tmp="$$(mktemp -d)"; trap 'rm -rf "$$tmp"' EXIT
	  : > "$$tmp/files"
	  while IFS= read -r rel; do
	    if should_pack "$$rel"; then echo "$$rel" >> "$$tmp/files"; fi
	  done < <(cd "$$pd" && find . -type f -printf '%P\n' | LC_ALL=C sort)
	  packed="$$(wc -l < "$$tmp/files")"
	  if [ "$$packed" -eq 0 ]; then echo "[ERROR] Packing failed: nothing to pack."; exit 1; fi
	  while IFS= read -r rel; do echo "  [+] Added: $$rel"; done < "$$tmp/files"
	}

	# Write to a temp file first so a crash never leaves a half-written .pk3 behind.
	# Deflate (-9) is the only method Xonotic reads; maximum level = smallest file.
	write_archive() {
	  temp_path="$$export_dir/$$output_name.tmp"
	  rm -f "$$temp_path"
	  if [ "$$packer" = zip ]; then
	    if ! (cd "$$pd" && zip -q -X -9 "$$temp_path" -@ < "$$tmp/files"); then echo "[ERROR] Packing failed."; rm -f "$$temp_path"; exit 1; fi
	  else
	    if ! bsdtar --format zip --options zip:compression=deflate,zip:compression-level=9 -cf "$$temp_path" -C "$$pd" -T "$$tmp/files" 2>/dev/null; then
	      if ! bsdtar --format zip --options zip:compression=deflate -cf "$$temp_path" -C "$$pd" -T "$$tmp/files"; then echo "[ERROR] Packing failed."; rm -f "$$temp_path"; exit 1; fi
	    fi
	  fi
	  mv -f "$$temp_path" "$$output_path"
	  size="$$(stat -c %s "$$output_path")"
	  echo; echo "[DONE] Created: $$output_path ($$(awk -v s="$$size" 'BEGIN { printf "%.2f", s / 1048576 }') MB)"
	  echo "[SUCCESS] Total files packed: $$packed"
	}

	# ---- Run -----------------------------------------------------------------------
	pick_packer
	detect_map_name
	# Remind about a missing thumbnail or music file before packing.
	check_extras "$$pd" "$$shown_name"

	if ! choose_rev; then echo "[INFO] Packing cancelled."; exit 0; fi
	prepare_target
	echo; echo "[INFO] Packaging contents of '$$project_name'..."
	echo "[INFO] Target archive: $$output_path"
	echo "[INFO] Including .map source: $$include_src"

	list_pack_files
	write_archive

# =============================================================================
# MAIN PROGRAM LOOP (start menu -> project menu)
# =============================================================================
menu:
	$(COMMON)
	PROJ=""

	list_projects() {
	  local w n; w="$$(cfg WORKSPACE)"
	  if [ ! -d "$$w" ]; then return 0; fi
	  find "$$w" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | LC_ALL=C sort | while IFS= read -r n; do
	    if [ -d "$$w/$$n/maps" ]; then
	      case "$$n" in .git|.github|.idea|.vscode|__pycache__) ;; *) echo "$$n";; esac
	    fi
	  done
	}

	print_header() { rule =; $(MAKE) -s -f "$(SELF)" banner; status_note; rule =; }

	print_main_menu() {
	  local w; w="$$(cfg WORKSPACE)"
	  echo; rule "="
	  echo "MAIN MENU"
	  echo "  Projects folder: $$w"
	  if [ ! -d "$$w" ]; then echo "  [WARNING] This folder does not exist - change it in the settings (s)."; fi
	  rule "="
	  echo "1) Choose map folder"
	  echo "2) Create new map folder"
	}

	# Pick an existing map folder by name or list number (result in PROJ).
	choose_project() {
	  local w entry lower n i; local -a projects
	  PROJ=""
	  while true; do
	    w="$$(cfg WORKSPACE)"
	    mapfile -t projects < <(list_projects)
	    if [ "$${#projects[@]}" -gt 0 ]; then
	      echo; echo "Projects found:"
	      i=1; for n in "$${projects[@]}"; do echo "  $$i) $$n"; i=$$((i+1)); done
	    else
	      echo; echo "[INFO] No map folders found yet in '$$w'."
	    fi
	    echo; ask "> Enter map directory name or number: "; entry="$$ANS"; lower="$${entry,,}"
	    case "$$lower" in
	      q) exit 0;;
	      h) show_help; continue;;
	      s) settings_menu; continue;;
	      c) return 1;;
	      "") continue;;
	    esac
	    if [ "$$entry" = . ] || [ "$$entry" = .. ] || [[ "$$entry" == */* ]]; then
	      echo "[ERROR] Please enter just the folder name, not a path."; continue
	    fi
	    if [ -d "$$w/$$entry" ]; then PROJ="$$entry"; return 0; fi
	    if [[ "$$entry" =~ ^[0-9]+$$ ]] && [ "$$entry" -ge 1 ] && [ "$$entry" -le "$${#projects[@]}" ]; then
	      PROJ="$${projects[$$((entry-1))]}"; return 0
	    fi
	    echo "[ERROR] Project directory '$$w/$$entry' not found!"
	  done
	}

	# Create a new map folder (result in PROJ so it can be opened right away).
	create_project() {
	  local w name lower err pdir s
	  PROJ=""
	  while true; do
	    w="$$(cfg WORKSPACE)"
	    if [ ! -d "$$w" ]; then
	      echo "[ERROR] Projects folder '$$w' does not exist!"
	      echo "        Change it in the settings (press 's')."
	      return 1
	    fi
	    echo; echo "--- Create new map folder ---"
	    echo " - It will be created in: $$w"
	    echo " - Allowed characters: letters, digits, '_' and '-'."
	    ask "> Enter new map folder name: "; name="$$ANS"; lower="$${name,,}"
	    case "$$lower" in
	      q) echo; echo "Goodbye!"; exit 0;;
	      h) show_help;;
	      s) settings_menu;;
	      c|x) echo "[INFO] Cancelled."; return 1;;
	      "") ;;
	      *) break;;
	    esac
	  done
	  if ! err="$$(validate_name "$$name")"; then echo "[ERROR] $$err"; return 1; fi
	  pdir="$$w/$$name"
	  if [ -e "$$pdir" ]; then
	    echo "[ERROR] '$$pdir' already exists - nothing was changed."
	    if [ -d "$$pdir" ] && confirm "> Open the existing folder instead?"; then PROJ="$$name"; return 0; fi
	    return 1
	  fi
	  if ! mkdir "$$pdir"; then echo "[ERROR] Could not create the folder structure"; return 1; fi
	  for s in "$${NEW_SUBDIRS[@]}"; do mkdir -p "$$pdir/$$s"; done
	  echo; echo "[DONE] Created map folder: $$pdir"
	  for s in "$${NEW_SUBDIRS[@]}"; do echo "  [DIR] $$name/$$s/"; done
	  PROJ="$$name"; return 0
	}

	act() { $(MAKE) -s -f "$(SELF)" "$$1" MAP="$$2" || true; }

	# Action menu for one project; returns on 'c'.
	project_menu() {
	  local map="$$1" pdir choice
	  while true; do
	    pdir="$$(cfg WORKSPACE)/$$map"
	    echo; rule "="
	    echo "Active Project: $$map"
	    status_note "$$pdir"
	    rule "="
	    echo "1) Export Assets"
	    echo "2) Rename Map"
	    echo "3) Pack it"
	    echo; ask "> Select option: "; choice="$${ANS,,}"
	    case "$$choice" in
	      1) act assets "$$map";;
	      2) tmpf=$$(mktemp)
	         RENAME_OUT="$$tmpf" $(MAKE) -s -f "$(SELF)" rename MAP="$$map" || true
	         if [ -s "$$tmpf" ]; then map=$$(cat "$$tmpf"); fi
	         rm -f "$$tmpf";;
	      3) act pk3 "$$map";;
	      s) settings_menu;;
	      h) show_help;;
	      c) echo "[INFO] Returning to main menu..."; return 0;;
	      q) echo; echo "Goodbye!"; exit 0;;
	      *) echo "[ERROR] Invalid option!";;
	    esac
	  done
	}

	print_header
	while true; do
	  print_main_menu
	  echo; ask "> Select option: "; choice="$${ANS,,}"
	  PROJ=""
	  case "$$choice" in
	    1) choose_project || true;;
	    2) create_project || true;;
	    h) show_help;;
	    s) settings_menu; print_header;;
	    q) echo; echo "Goodbye!"; exit 0;;
	    c|"") continue;;
	    *) echo "[ERROR] Invalid option!";;
	  esac
	  if [ -n "$$PROJ" ]; then project_menu "$$PROJ"; fi
	done
