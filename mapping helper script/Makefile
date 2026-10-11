# =============================================================================
# XONOTIC MAPPING HELPER  (GNU Make edition)
# =============================================================================
#
# Port of mapping_helper.py. Same menus, same behaviour, no Python needed.
#
#   1) Export Textures - scan the .map (classic + brush-primitive format, brush
#                        faces + patches) and your scripts/*.shader files, then
#                        copy every texture found in the Xonotic "mapping
#                        support" PK3s into your project (never overwrites).
#   2) Change Revision - rename the map files + lightmap folder in maps/ and
#                        update the title in the .mapinfo (preview + confirm).
#   3) Clean Backups   - remove .bak / .autosave files in maps/.
#   4) Pack it         - build a .pk3 (.map source optional). Only the PK3 name
#                        gets a revision; the files inside keep their names.
#
# REQUIREMENTS: GNU make, bash >= 4.4, unzip, zip OR bsdtar, GNU grep (-P), awk, find
#   Arch/CachyOS:  sudo pacman -S make unzip   (+ zip, or bsdtar which is usually there)
#
# USAGE (put this Makefile next to your map project folders):
#   make                       interactive menu (start menu -> project menu)
#   make textures MAP=Name     run one action directly (still interactive
#   make revision MAP=Name     where the original asks questions)
#   make clean-backups MAP=Name
#   make pk3 MAP=Name
#   make new NAME=Name         create a new map folder (Xonotic layout)
#   make settings              settings menu
#   make help                  help screen
#
# SETTINGS are stored in 'mapping_helper.conf' next to this Makefile (Make
# syntax instead of JSON, so no extra tools are needed). Change them in the
# settings menu (press 's'). Keys: EXPORT_DIR, PK3_PREFIX, REV_PREFIX,
# XONOTIC_DATA_DIR, INCLUDE_MAP_SOURCE (yes/no), PROJECTS_DIR,
# SEARCH_ALL_PK3S (yes/no: also search your own PK3s in the data folder).
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
INCLUDE_MAP_SOURCE ?= yes
SEARCH_ALL_PK3S    ?= yes
PROJECTS_DIR       ?=
-include $(CONF)

# Effective projects folder: the setting, else the folder of this Makefile.
WORKSPACE   = $(or $(strip $(PROJECTS_DIR)),$(MK_DIR))
MAP        ?=
NAME       ?=
KEY        ?=
VALUE      ?=
PROJECT_DIR = $(WORKSPACE)/$(MAP)

.PHONY: menu banner help settings get set new check-map textures revision clean-backups pk3

# =============================================================================
# SHARED SHELL HELPERS (expanded into every recipe)
# =============================================================================
define COMMON
NEW_SUBDIRS=(maps textures scripts sound models env gfx)
TOOL_TEXTURES=(common/caulk common/nodraw common/clip common/fullclip common/weapclip common/botclip common/trigger common/hint common/hintskip common/skip common/origin common/areaportal common/clusterportal common/donotenter common/nodrop common/noimpact common/nolightmap common/nonsolid common/structural)
MAP_SUFFIXES=("" _alpha _gloss _glow _glow_alpha _norm _norm_alpha _pants _shirt)
IMAGE_EXTS=(.png .tga .jpg .dds)

trim() { local s="$$1"; s="$${s#"$${s%%[![:space:]]*}"}"; s="$${s%"$${s##*[![:space:]]}"}"; printf '%s' "$$s"; }
rule() { printf '%*s\n' 75 '' | tr ' ' "$$1"; }

# ask <prompt>: result in ANS. EOF (Ctrl+D) quits cleanly.
ask() { ANS=""; if ! read -r -p "$$1" ANS; then echo; echo "Goodbye!"; exit 0; fi; ANS="$$(trim "$$ANS")"; }
# confirm <question>: anything except y/yes counts as no.
confirm() { ask "$$1 [y/N]: "; case "$${ANS,,}" in y|yes) return 0;; *) return 1;; esac; }

# cfg <KEY>: read a fresh effective value (settings may change while running).
cfg() { $(MAKE) -s -f "$(SELF)" get KEY="$$1"; }
# setcfg <KEY> <VALUE>: store a setting in mapping_helper.conf.
setcfg() { $(MAKE) -s -f "$(SELF)" set KEY="$$1" VALUE="$$2" >/dev/null; }

# Xonotic data folder: configured one, else first existing default, else Linux default.
datadir() {
  local d="$(strip $(XONOTIC_DATA_DIR))" c
  if [ -n "$$d" ]; then printf '%s' "$$d"; return 0; fi
  for c in "$$HOME/.xonotic/data" "$$HOME/Saved Games/xonotic/data" "$$HOME/Library/Application Support/xonotic/data"; do
    if [ -d "$$c" ]; then printf '%s' "$$c"; return 0; fi
  done
  printf '%s' "$$HOME/.xonotic/data"
}

# Revision prefix: '_r', 'r' and ' r ' all become 'r'.
revprefix() { printf '%s' "$(REV_PREFIX)" | sed 's/^[[:space:]_]*//;s/[[:space:]]*$$//'; }

# PK3s to export textures from, one per line. 'Support' PK3s (name contains
# 'mapping' or 'extra') come first, then - if SEARCH_ALL_PK3S is yes - all other
# *.pk3 in the data folder (e.g. your own texture packs). First archive wins.
support_pk3s() {
  local d f n all; d="$$(datadir)"
  if [ ! -d "$$d" ]; then return 0; fi
  all="$$(yesno "$(strip $(SEARCH_ALL_PK3S))")"
  shopt -s nullglob
  local -a sup=() oth=()
  for f in "$$d"/*.pk3; do
    n="$${f##*/}"; n="$${n,,}"
    case "$$n" in *mapping*|*extra*) sup+=("$$f");; *) oth+=("$$f");; esac
  done
  for f in "$${sup[@]}"; do printf '%s\n' "$$f"; done | LC_ALL=C sort
  if [ "$$all" = yes ]; then
    for f in "$${oth[@]}"; do printf '%s\n' "$$f"; done | LC_ALL=C sort
  fi
}

# Editor backups: '*.bak', '*.autosave', '*.autosave.map', ...
is_backup() { local l="$${1,,}"; case "$$l" in *.bak|*.autosave*) return 0;; *) return 1;; esac; }

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

# split_revision <stem> <prefix>: sets CORE and OLDREV ('mymap_r3' -> 'mymap' + '_r3').
split_revision() {
  local stem="$$1" rp="$$2" m="" re
  CORE="$$stem"; OLDREV=""
  shopt -s nocasematch
  re="_$$rp[0-9]+[a-z]*$$"
  if [[ "$$stem" =~ $$re ]]; then m="$${BASH_REMATCH[0]}"
  else
    re="_[a-z]*[0-9]+[a-z]*$$"
    if [[ "$$stem" =~ $$re ]]; then m="$${BASH_REMATCH[0]}"; fi
  fi
  shopt -u nocasematch
  if [ -n "$$m" ]; then CORE="$${stem:0:$${#stem}-$${#m}}"; OLDREV="$$m"; fi
}

# prompt_tag <prompt> <rev_prefix> [default]: result in TAG; returns 1 if cancelled/invalid.
prompt_tag() {
  local rp="$${2,,}" t
  ask "$$1"; t="$${ANS,,}"; t="$$(printf '%s' "$$t" | sed 's/^_*//')"
  if [ -z "$$t" ] && [ "$$#" -ge 3 ]; then TAG="$$3"; return 0; fi
  case "$$t" in c|x|q|"") return 1;; esac
  case "$$t" in h|s) echo "[ERROR] '$$t' is a menu command, not a revision tag. Nothing was changed."; return 1;; esac
  if [ -n "$$rp" ] && [[ "$$t" == "$$rp"* ]] && [[ "$${t:$${#rp}:1}" =~ ^[0-9]$$ ]]; then t="$${t:$${#rp}}"; fi
  if ! [[ "$$t" =~ ^[a-z0-9]+$$ ]]; then echo "[ERROR] The tag may only contain letters and digits."; return 1; fi
  TAG="$$t"; return 0
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

# update_mapinfo <file> <core> <old_rev> <new_rev>: only the first 'title' line is touched.
update_mapinfo() {
  local f="$$1" tmpf; tmpf="$$(mktemp)"
  LC_ALL=C awk -v core="$$2" -v old="$$3" -v nw="$$4" '
    BEGIN { found = 0 }
    {
      if (!found) {
        body = $$0; tail = ""
        if (match(body, /[ \t\r]*$$/)) { tail = substr(body, RSTART); body = substr(body, 1, RSTART - 1) }
        lb = tolower(body)
        if (match(lb, /^[ \t]*title[ \t]+/)) {
          found = 1
          hd = substr(body, 1, RLENGTH)
          val = substr(body, RLENGTH + 1)
          if (old != "" && length(val) >= length(old) && substr(val, length(val) - length(old) + 1) == old) {
            val = substr(val, 1, length(val) - length(old)); sub(/[ \t]+$$/, "", val)
          }
          $$0 = hd val " " nw tail
        }
      }
      print
    }
    END { if (!found) print "title " core " " nw }
  ' "$$f" > "$$tmpf"
  cat "$$tmpf" > "$$f"; rm -f "$$tmpf"
}

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

# validate_name <name>: prints a message and returns 1 if unusable.
validate_name() {
  local n="$$1"
  case "$${n,,}" in c|h|q|s|x) echo "'$$n' is reserved for menu commands (h, s, c, q, x)."; return 1;; esac
  if ! [[ "$$n" =~ ^[A-Za-z0-9_-]+$$ ]]; then echo "Use only letters, digits, '_' and '-' (no spaces or other characters)."; return 1; fi
  case "$$n" in .git|.github|.idea|.vscode|__pycache__) echo "'$$n' is a reserved name."; return 1;; esac
  return 0
}

yesno() { case "$${1,,}" in yes|true|1) printf yes;; *) printf no;; esac; }

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
  echo; rule =
  echo "                      HELP MENU"
  rule =
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
  echo "1) Export Textures:"
  echo "   Scans the .map (brush faces + patches) and your scripts/*.shader files"
  echo "   and copies the matching textures - including _glow, _norm, _gloss, ..."
  echo "   companions and skybox faces - from the PK3s in your Xonotic data folder"
  echo "   (support PKs first, then your own PK3s; see settings, option 7)"
  echo "   into the project. If a texture is defined by a shader in one of those"
  echo "   PK3s (scripts/*.shader), that script is copied to scripts/ too, plus the"
  echo "   images it uses. Existing files are never overwritten."
  echo
  echo "2) Change Revision:"
  echo "   Renames the map files and the lightmap folder in maps/ and updates the"
  echo "   .mapinfo title (format: $$rs). Shows a preview first."
  echo
  echo "3) Clean Backups:"
  echo "   Lists and (after confirmation) deletes .bak / .autosave files in maps/."
  echo
  echo "4) Pack it:"
  echo "   Builds a .pk3 from the project (prefix: $$ps). Compiler leftovers,"
  echo "   backups and working files (.prt, .srf, .xcf, ...) are left out. The"
  echo "   maps/*.map source is included unless disabled in the settings."
  echo "   You are asked whether the .pk3 name should get a revision number. If"
  echo "   one exists already, you can raise it by 1 or enter your own. The map"
  echo "   files inside the package keep their names."
  echo
  echo "Global Commands:"
  echo "   h = help | s = settings | c = cancel / back | q = quit"
  rule =
}

settings_menu() {
  local ed pf rv dd src pd sa choice value np bad
  while true; do
    ed="$$(cfg EXPORT_DIR)"; pf="$$(cfg PK3_PREFIX)"; rv="$$(cfg REV_PREFIX)"
    dd="$$(cfg XONOTIC_DATA_DIR)"; src="$$(yesno "$$(cfg INCLUDE_MAP_SOURCE)")"; pd="$$(cfg PROJECTS_DIR)"
    sa="$$(yesno "$$(cfg SEARCH_ALL_PK3S)")"
    echo; rule =
    echo "                  SETTINGS MENU"
    status_note
    rule =
    echo "1) PK3 Export Path:      $${ed:-[Not set - saves inside map folder]}"
    if [ -n "$$pf" ]; then echo "2) PK3 Filename Prefix:  '$$pf'"; else echo "2) PK3 Filename Prefix:  [Not set - None]"; fi
    if [ -n "$$rv" ]; then echo "3) Revision Format:      '$$rv'"; else echo "3) Revision Format:      [Not set - None]"; fi
    if [ -n "$$dd" ]; then echo "4) Xonotic Data Folder:  $$dd"; else echo "4) Xonotic Data Folder:  [Auto-detect: $$(datadir)]"; fi
    echo "5) Include .map in PK3:  $$src"
    if [ -n "$$pd" ]; then echo "6) Projects Folder:      $$pd"; else echo "6) Projects Folder:      [Default: $(MK_DIR)]"; fi
    if [ "$$sa" = yes ]; then echo "7) Search all PK3s:      yes"; else echo "7) Search all PK3s:      no (support PKs only)"; fi
    rule -
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
        echo " - Enter the letters placed before the revision number,"
        echo "   e.g. 'r' gives mymap_r3, 'v' gives mymap_v3."
        echo " - Press Enter without typing anything to use plain numbers (mymap_3)."
        ask "> Enter revision prefix: "; value="$$(printf '%s' "$$ANS" | sed 's/^[[:space:]_]*//;s/[[:space:]]*$$//')"
        case "$${value,,}" in c|x|q) continue;; esac
        if ! [[ "$$value" =~ ^[A-Za-z]*$$ ]]; then echo "[ERROR] Only letters are allowed (an underscore is added automatically)."; continue; fi
        setcfg REV_PREFIX "$$value"; echo "[SUCCESS] Revision format updated to: '$$value'" ;;
      4)
        echo; echo "--- Set Xonotic Data Folder ---"
        echo " - Folder that contains your support PK3s (e.g. ~/.xonotic/data)."
        echo " - Type 'default' or press Enter to use auto-detection."
        ask "> Enter path: "; value="$$ANS"
        case "$${value,,}" in c|x|q) continue;; esac
        if [ -z "$$value" ] || [ "$${value,,}" = default ]; then
          setcfg XONOTIC_DATA_DIR ""; echo "[SUCCESS] Using auto-detection again."
        else
          np="$$(realpath -m -- "$${value/#\~/$$HOME}")"
          if [ ! -d "$$np" ]; then echo "[ERROR] '$$np' does not exist or is not a folder!"
          else setcfg XONOTIC_DATA_DIR "$$np"; echo "[SUCCESS] Xonotic data folder saved: $$np"; fi
        fi ;;
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
      7)
        if [ "$$sa" = yes ]; then setcfg SEARCH_ALL_PK3S no; echo "[SUCCESS] Textures are searched in the support PKs only."
        else setcfg SEARCH_ALL_PK3S yes; echo "[SUCCESS] Textures are searched in ALL PK3s of the data folder (support PKs first)."; fi ;;
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
	  DATA_DIR) datadir;;
	  EXPORT_DIR|PK3_PREFIX|REV_PREFIX|XONOTIC_DATA_DIR|PROJECTS_DIR|INCLUDE_MAP_SOURCE|SEARCH_ALL_PK3S) printf '%s' "$($(KEY))";;
	esac

# Store a setting in mapping_helper.conf (an empty VALUE resets it).
set:
	case "$(KEY)" in EXPORT_DIR|PK3_PREFIX|REV_PREFIX|XONOTIC_DATA_DIR|PROJECTS_DIR|INCLUDE_MAP_SOURCE|SEARCH_ALL_PK3S) ;; *) echo "[ERROR] Unknown setting '$(KEY)'" >&2; exit 1;; esac
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
# 1) EXPORT TEXTURES
# =============================================================================
textures: check-map
	$(COMMON)
	maps_dir="$(PROJECT_DIR)/maps"
	if [ ! -d "$$maps_dir" ]; then echo "[ERROR] Subfolder '$$maps_dir' does not exist!"; exit 1; fi
	pick_map_file "$$maps_dir" || exit 0
	map_file="$$MAPFILE"
	echo; echo "[INFO] Analyzing map file: $${map_file##*/}..."
	tmp="$$(mktemp -d)"; trap 'rm -rf "$$tmp"' EXIT
	printf '%s\n' "$${TOOL_TEXTURES[@]}" > "$$tmp/tools"

	# --- 1) What does the map use? Brush faces (classic + brush primitives)
	#        and patches ('patchDef2/3' + '{' + a line holding the texture).
	{
	  grep -oP '^\s*\(\s*[^)]+\)\s*\(\s*[^)]+\)\s*\(\s*[^)]+\)\s*(?:\(\s*\(\s*[^)]*\)\s*\(\s*[^)]*\)\s*\)\s*)?\K("[^"]+"|\S+)' "$$map_file" || true
	  LC_ALL=C awk '
	    expect { s = $$0; gsub(/^[ \t\r]+/, "", s); gsub(/[ \t\r]+$$/, "", s); if (s == "" || s == "{") next; expect = 0; print s; next }
	    { s = tolower($$0); gsub(/^[ \t\r]+/, "", s); if (s ~ /^patchdef[23]/) expect = 1 }
	  ' "$$map_file"
	} | tr 'A-Z' 'a-z' | tr '\\' '/' | tr -d '"' | sed -E 's/\.(png|tga|jpg|dds)$$//' | grep -v -E '^$$|^\(|^\)|^noshader' | grep -v -x -F -f "$$tmp/tools" | awk '{ if (index($$0, "textures/") == 1) print; else print "textures/" $$0 }' | LC_ALL=C sort -u > "$$tmp/brush" || true
	echo "[SUCCESS] Found $$(wc -l < "$$tmp/brush") unique textures in the .map file."

	# --- 2) Own shaders of this project + the images of the shaders the map USES.
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
	grep -x -F -f "$$tmp/defined" "$$tmp/brush" > "$$tmp/custom" || true
	ncustom="$$(wc -l < "$$tmp/custom")"
	if [ "$$ncustom" -gt 0 ]; then echo "[INFO] $$ncustom texture name(s) are your own shaders (images are taken from the shader files instead)."; fi
	awk -F'\t' 'NR == FNR { want[$$0] = 1; next } $$1 == "R" && ($$2 in want) { print $$3 }' "$$tmp/custom" "$$tmp/ownrows" | LC_ALL=C sort -u > "$$tmp/refs"
	grep -v -x -F -f "$$tmp/defined" "$$tmp/brush" > "$$tmp/b2" || true

	# --- 3) Where can we get images from? Index all support PK3s ONCE.
	mapfile -t pks < <(support_pk3s)
	if [ "$${#pks[@]}" -eq 0 ]; then
	  echo "[ERROR] No PK3s found in '$$(datadir)'!"
	  echo "        Set the correct folder in the settings menu (press 's')."
	  exit 1
	fi
	if [ "$${#pks[@]}" -le 10 ]; then
	  names=""; for p in "$${pks[@]}"; do names="$$names$${names:+, }'$${p##*/}'"; done
	  echo "[INFO] Scanning $${#pks[@]} archive(s): [$$names]"
	else
	  echo "[INFO] Scanning $${#pks[@]} archives in '$$(datadir)' (this can take a moment)..."
	fi
	: > "$$tmp/index.raw"
	for p in "$${pks[@]}"; do
	  if ! unzip -Z1 "$$p" 2>/dev/null | LC_ALL=C awk -v pk="$$p" '!/\/$$/ { print tolower($$0) "\t" pk "\t" $$0 }' >> "$$tmp/index.raw"; then
	    echo "[WARNING] Skipping unreadable archive $${p##*/}"
	  fi
	done
	awk -F'\t' '!seen[$$1]++' "$$tmp/index.raw" > "$$tmp/index"
	declare -A IDXP=() IDXN=()
	while IFS=$$'\t' read -r k p n; do IDXP["$$k"]="$$p"; IDXN["$$k"]="$$n"; done < "$$tmp/index"

	# --- 3b) Textures that are shaders defined inside a PK3 (sprites, alpha, sky, ...):
	#         the shader script is copied to scripts/ and the images that shader uses are exported.
	: > "$$tmp/provided"; : > "$$tmp/pk3refs"; : > "$$tmp/shfiles"
	declare -A PROV=()
	if [ -s "$$tmp/b2" ]; then
	  mkdir -p "$$tmp/sh"; n=0
	  while IFS=$$'\t' read -r k pk real; do
	    n=$$((n+1))
	    unzip -p "$$pk" "$$real" > "$$tmp/sh/$$n.shader" 2>/dev/null || continue
	    if ! grep -q -i -F -f "$$tmp/b2" "$$tmp/sh/$$n.shader"; then rm -f "$$tmp/sh/$$n.shader"; continue; fi
	    parse_shader "$$tmp/sh/$$n.shader" > "$$tmp/pp"
	    while IFS= read -r nm; do
	      if [ -z "$${PROV[$$nm]+x}" ] && grep -q -x -F -- "$$nm" "$$tmp/b2"; then
	        PROV["$$nm"]=1
	        echo "$$nm" >> "$$tmp/provided"
	        awk -F'\t' -v n="$$nm" '$$1 == "R" && $$2 == n { print $$3 }' "$$tmp/pp" >> "$$tmp/pk3refs"
	        printf '%s\t%s\t%s\n' "$$pk" "$$real" "$$nm" >> "$$tmp/shfiles"
	      fi
	    done < <(awk -F'\t' '$$1 == "D" { print $$2 }' "$$tmp/pp")
	    rm -f "$$tmp/sh/$$n.shader"
	  done < <(awk -F'\t' '$$1 ~ /^scripts\/.*\.shader$$/' "$$tmp/index")
	fi
	grep -v -x -F -f "$$tmp/provided" "$$tmp/b2" > "$$tmp/b3" || true
	nprov="$$(wc -l < "$$tmp/provided")"
	nsh="$$(cut -f1,2 "$$tmp/shfiles" | LC_ALL=C sort -u | wc -l)"
	if [ "$$nprov" -gt 0 ]; then echo "[INFO] $$nprov texture name(s) are defined by shaders in PK3s ($$nsh shader script(s) will be copied to scripts/)."; fi
	# Everything we should try to find as an image file.
	cat "$$tmp/b3" "$$tmp/refs" "$$tmp/pk3refs" | LC_ALL=C sort -u > "$$tmp/needed"

	# --- 4) Copy everything we can find (never overwrite, never leave the project).
	root="$$(realpath "$(PROJECT_DIR)")"
	copied=0; skipped=0; shcopied=0; missing=()
	# Shader scripts first (never overwritten, never outside the project).
	while IFS=$$'\t' read -r pk real; do
	  names="$$(awk -F'\t' -v p="$$pk" -v r="$$real" '$$1 == p && $$2 == r { print $$3 }' "$$tmp/shfiles" | paste -sd, - | sed 's/,/, /g')"
	  target="$(PROJECT_DIR)/$$real"
	  rt="$$(realpath -m -- "$$target")"
	  case "$$rt" in "$$root"/*) ;; *) continue;; esac
	  if [ -e "$$target" ]; then
	    echo "  [!] Shader script already exists, not overwritten: $$real"
	    echo "      It does not define: $$names"
	    continue
	  fi
	  mkdir -p "$$(dirname "$$target")"
	  unzip -p "$$pk" "$$real" > "$$target"
	  echo "  [+] Copied shader ($${pk##*/}): $$real  (defines: $$names)"
	  shcopied=$$((shcopied+1))
	done < <(cut -f1,2 "$$tmp/shfiles" | awk -F'\t' '!seen[$$1 FS $$2]++' | LC_ALL=C sort -s -t$$'\t' -k2,2)
	while IFS= read -r base; do
	  if [ -z "$$base" ]; then continue; fi
	  found=0
	  for suf in "$${MAP_SUFFIXES[@]}"; do
	    for ext in "$${IMAGE_EXTS[@]}"; do
	      key="$$base$$suf$$ext"
	      if [ -n "$${IDXP[$$key]+x}" ]; then
	        found=1; pk="$${IDXP[$$key]}"; real="$${IDXN[$$key]}"
	        target="$(PROJECT_DIR)/$$real"
	        rt="$$(realpath -m -- "$$target")"
	        case "$$rt" in "$$root"/*) ;; *) continue;; esac
	        if [ -e "$$target" ]; then skipped=$$((skipped+1)); continue; fi
	        mkdir -p "$$(dirname "$$target")"
	        unzip -p "$$pk" "$$real" > "$$target"
	        echo "  [+] Copied ($${pk##*/}): $$real"
	        copied=$$((copied+1))
	      fi
	    done
	  done
	  if [ "$$found" -eq 0 ]; then missing+=("$$base"); fi
	done < "$$tmp/needed"

	# --- 5) Report.
	if [ "$${#missing[@]}" -gt 0 ]; then
	  echo; echo "[INFO] No matching image found in the searched PK3s for:"
	  for m in "$${missing[@]}"; do echo "  [?] $$m"; done
	  echo "      These are usually shipped with the base game or defined by a"
	  echo "      shader (check any that you expected to be exported)."
	fi
	echo; echo "[DONE] Copied $$copied file(s) and $$shcopied shader script(s), skipped $$skipped that already exist."
	echo "[NOTE] Shader scripts are copied as a whole file, so they may also contain"
	echo "       shaders you do not use. Only images of the shaders your map uses"
	echo "       are exported."

# =============================================================================
# 2) CHANGE REVISION
# =============================================================================
revision: check-map
	$(COMMON)
	maps_dir="$(PROJECT_DIR)/maps"
	if [ ! -d "$$maps_dir" ]; then echo "[ERROR] Directory '$$maps_dir' does not exist!"; exit 1; fi
	prefix="$$(revprefix)"
	pick_map_file "$$maps_dir" || exit 0
	current_base="$${MAPFILE##*/}"; current_base="$${current_base%.map}"
	split_revision "$$current_base" "$$prefix"
	core="$$CORE"; old_rev="$$OLDREV"
	echo; echo "[INFO] Current name: $$current_base  (base: '$$core', revision: '$${old_rev:-none}')"
	if ! prompt_tag "> Enter new revision tag: " "$$prefix"; then echo "[INFO] Revision change cancelled."; exit 0; fi
	new_rev="_$$prefix$$TAG"; new_base="$$core$$new_rev"
	if [ "$$new_base" = "$$current_base" ]; then echo "[INFO] That is already the current revision. Nothing to do."; exit 0; fi

	# Everything in maps/ that belongs to the current base name (files + lightmap folder).
	SRC=(); DST=()
	while IFS= read -r e; do
	  if starts_with_base "$$e" "$$current_base"; then SRC+=("$$e"); DST+=("$$new_base$${e:$${#current_base}}"); fi
	done < <(find "$$maps_dir" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)

	# Refuse to run if a target already exists (and is not itself being renamed).
	clashes=()
	for d in "$${DST[@]}"; do
	  if [ -e "$$maps_dir/$$d" ]; then
	    insrc=0; for s in "$${SRC[@]}"; do if [ "$$s" = "$$d" ]; then insrc=1; fi; done
	    if [ "$$insrc" -eq 0 ]; then clashes+=("$$d"); fi
	  fi
	done
	if [ "$${#clashes[@]}" -gt 0 ]; then
	  echo "[ERROR] These targets already exist, nothing was changed:"
	  for d in "$${clashes[@]}"; do echo "  - $$d"; done
	  exit 1
	fi

	echo; echo "The following renames will be performed:"
	for i in "$${!SRC[@]}"; do
	  if [ -d "$$maps_dir/$${SRC[$$i]}" ]; then kind="DIR "; else kind="FILE"; fi
	  echo "  [$$kind] $${SRC[$$i]}  ->  $${DST[$$i]}"
	done
	echo "  [INFO] The title in '$$new_base.mapinfo' (if present) will end with '$$new_rev'."
	echo
	if ! confirm "> Proceed?"; then echo "[INFO] Revision change cancelled. Nothing was changed."; exit 0; fi

	# Stop at the first error so the state stays understandable.
	for i in "$${!SRC[@]}"; do
	  if ! mv -- "$$maps_dir/$${SRC[$$i]}" "$$maps_dir/$${DST[$$i]}"; then
	    echo "[ERROR] Could not rename '$${SRC[$$i]}'"
	    echo "        Stopped. Some files may already have been renamed."
	    exit 1
	  fi
	done

	mapinfo="$$maps_dir/$$new_base.mapinfo"
	if [ -f "$$mapinfo" ]; then
	  update_mapinfo "$$mapinfo" "$$core" "$$old_rev" "$$new_rev"
	  echo "  [INFO] Updated .mapinfo title with '$$new_rev'."
	else
	  echo "  [INFO] No .mapinfo found for this map - title not updated."
	fi
	echo; echo "[DONE] Revision successfully updated to '$$new_rev'."

# =============================================================================
# 3) CLEAN BACKUPS (maps/ only)
# =============================================================================
clean-backups: check-map
	$(COMMON)
	maps_dir="$(PROJECT_DIR)/maps"
	if [ ! -d "$$maps_dir" ]; then echo "[ERROR] Directory '$$maps_dir' does not exist!"; exit 1; fi
	backups=()
	while IFS= read -r f; do
	  if is_backup "$$f"; then backups+=("$$f"); fi
	done < <(find "$$maps_dir" -mindepth 1 -maxdepth 1 -type f -printf '%f\n' | LC_ALL=C sort)
	if [ "$${#backups[@]}" -eq 0 ]; then echo; echo "[INFO] No backup files found."; exit 0; fi
	echo; echo "The following backup files will be deleted:"
	for f in "$${backups[@]}"; do echo "  - $$f"; done
	echo "  (Tip: an .autosave can be your last rescue after an editor crash.)"
	echo
	if ! confirm "> Delete these files?"; then echo "[INFO] Nothing was deleted."; exit 0; fi
	deleted=0
	for f in "$${backups[@]}"; do
	  if rm -- "$$maps_dir/$$f" 2>/dev/null; then echo "  [DEL] Removed: $$f"; deleted=$$((deleted+1)); else echo "  [ERROR] Could not delete $$f"; fi
	done
	echo; echo "[DONE] Cleaned up $$deleted backup file(s)."

# =============================================================================
# 4) PACK IT
# =============================================================================
pk3: check-map
	$(COMMON)
	# Packer: Info-ZIP 'zip' if installed, else bsdtar (libarchive). Both write Deflate.
	if command -v zip >/dev/null; then packer=zip
	elif command -v bsdtar >/dev/null; then packer=bsdtar
	else echo "[ERROR] Neither 'zip' nor 'bsdtar' found (sudo pacman -S zip)"; exit 1; fi
	pd="$(PROJECT_DIR)"; maps_dir="$$pd/maps"; project_name="$(MAP)"
	include_src="$$(yesno "$(strip $(INCLUDE_MAP_SOURCE))")"

	# Map name for the file name: prefer the compiled .bsp (newest).
	map_base="$${project_name,,}"
	bsps=()
	if [ -d "$$maps_dir" ]; then
	  while IFS= read -r b; do bsps+=("$$b"); done < <(find "$$maps_dir" -maxdepth 1 -type f -name '*.bsp' -printf '%T@ %f\n' | sort -rn | sed 's/^[^ ]* //')
	fi
	if [ "$${#bsps[@]}" -gt 0 ]; then
	  b="$${bsps[0]%.bsp}"; map_base="$${b,,}"
	  if [ "$${#bsps[@]}" -gt 1 ]; then echo "[WARNING] Several .bsp files found; using the newest: $${bsps[0]}"; fi
	else
	  src1=""
	  if [ -d "$$maps_dir" ]; then src1="$$(find_maps "$$maps_dir" | head -n 1)"; fi
	  if [ -n "$$src1" ]; then b="$${src1%.map}"; map_base="$${b,,}"; fi
	  echo "[WARNING] No compiled .bsp found in maps/ - the package would not be playable."
	  if ! confirm "> Pack anyway?"; then echo "[INFO] Packing cancelled."; exit 0; fi
	fi

	# Target folder and file name: prefix + name (+ revision).
	prefix="$(strip $(PK3_PREFIX))"
	rev_prefix="$$(revprefix)"
	custom="$(strip $(EXPORT_DIR))"
	if [ -n "$$custom" ]; then export_dir="$$custom"; else export_dir="$$pd"; fi

	# Ask whether the PK3 name should carry a revision (files inside keep their names).
	choose_rev() {
	  echo
	  if ! confirm "> Add a revision number to the PK3 file name?"; then PK3_BASE="$$map_base"; REVISION=""; return 0; fi
	  split_revision "$$map_base" "$$rev_prefix"
	  local core="$$CORE" name_rev="$$OLDREV" lhead f n ln rest num cur k choice tag
	  local -A EX=()
	  lhead="$$prefix$${core}_$$rev_prefix"; lhead="$${lhead,,}"
	  shopt -s nullglob
	  if [ -d "$$export_dir" ]; then
	    for f in "$$export_dir"/*.pk3; do
	      n="$${f##*/}"; ln="$${n,,}"
	      if [[ "$$ln" == "$$lhead"* ]]; then
	        rest="$${ln#"$$lhead"}"
	        if [[ "$$rest" =~ ^([0-9]+)\.pk3$$ ]]; then EX[$$((10#$${BASH_REMATCH[1]}))]="$$n"; fi
	      fi
	    done
	  fi
	  if [ -n "$$name_rev" ]; then
	    echo "[INFO] The map files are named '$$map_base' (revision '$$name_rev'). The files inside stay unchanged; the PK3 name uses '$$core'."
	    if [[ "$$name_rev" =~ [0-9]+ ]]; then
	      num=$$((10#$${BASH_REMATCH[0]}))
	      if [ -z "$${EX[$$num]+x}" ]; then EX[$$num]="map file name '$$map_base'"; fi
	    fi
	  fi
	  if [ "$${#EX[@]}" -gt 0 ]; then
	    cur=-1; for k in "$${!EX[@]}"; do if [ "$$k" -gt "$$cur" ]; then cur="$$k"; fi; done
	    echo "[INFO] Current revision: _$$rev_prefix$$cur  (found: $${EX[$$cur]})"
	    echo "  1) Increase by 1  ->  _$$rev_prefix$$((cur+1))"
	    echo "  2) Enter my own"
	    ask "> Select option: "; choice="$${ANS,,}"
	    case "$$choice" in
	      c|x|q) return 1;;
	      ""|1) tag="$$((cur+1))";;
	      2) if ! prompt_tag "> Enter revision tag: " "$$rev_prefix"; then return 1; fi; tag="$$TAG";;
	      *) echo "[ERROR] Invalid selection."; return 1;;
	    esac
	  else
	    echo "[INFO] No existing revision found."
	    if ! prompt_tag "> Enter revision tag: " "$$rev_prefix" "1"; then return 1; fi
	    tag="$$TAG"
	  fi
	  PK3_BASE="$$core"; REVISION="_$$rev_prefix$$tag"
	}
	if ! choose_rev; then echo "[INFO] Packing cancelled."; exit 0; fi
	output_name="$$prefix$$PK3_BASE$$REVISION.pk3"

	mkdir -p "$$export_dir"
	export_dir="$$(realpath "$$export_dir")"
	output_path="$$export_dir/$$output_name"
	if [ -e "$$output_path" ]; then
	  echo
	  if ! confirm "> '$$output_name' already exists. Overwrite?"; then echo "[INFO] Packing cancelled. Nothing was changed."; exit 0; fi
	fi

	echo; echo "[INFO] Packaging contents of '$$project_name'..."
	echo "[INFO] Target archive: $$output_path"
	echo "[INFO] Including .map source: $$include_src"

	# File list (sorted), filtered by the packing rules.
	tmp="$$(mktemp -d)"; trap 'rm -rf "$$tmp"' EXIT
	: > "$$tmp/files"
	while IFS= read -r rel; do
	  if should_pack "$$rel"; then echo "$$rel" >> "$$tmp/files"; fi
	done < <(cd "$$pd" && find . -type f -printf '%P\n' | LC_ALL=C sort)
	packed="$$(wc -l < "$$tmp/files")"
	if [ "$$packed" -eq 0 ]; then echo "[ERROR] Packing failed: nothing to pack."; exit 1; fi
	while IFS= read -r rel; do echo "  [+] Added: $$rel"; done < "$$tmp/files"

	# Write to a temp file first so a crash never leaves a half-written .pk3 behind.
	# Deflate (-9) is the only method Xonotic reads; maximum level = smallest file.
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
	  echo; rule =
	  echo "MAIN MENU"
	  echo "  Projects folder: $$w"
	  if [ ! -d "$$w" ]; then echo "  [WARNING] This folder does not exist - change it in the settings (s)."; fi
	  rule =
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
	    echo; rule =
	    echo "Active Project: $$map"
	    status_note "$$pdir"
	    rule =
	    echo "1) Export Textures"
	    echo "2) Change Revision"
	    echo "3) Clean Backups"
	    echo "4) Pack it"
	    echo; ask "> Select option: "; choice="$${ANS,,}"
	    case "$$choice" in
	      1) act textures "$$map";;
	      2) act revision "$$map";;
	      3) act clean-backups "$$map";;
	      4) act pk3 "$$map";;
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
