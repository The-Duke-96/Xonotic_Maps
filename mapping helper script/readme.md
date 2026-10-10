# Xonotic Mapping Helper

A small terminal tool for Xonotic mappers that handles the repetitive housekeeping of a map project. Single Python file, no dependencies.

What it does:
Export Textures – copies the textures used by your .map and your own shaders from the Xonotic mapping support packages into your project (including _glow, _norm, _gloss, ... and skybox images).
Change Revision – renames map files and the lightmap folder to a new revision (mymap_r2 -> mymap_r3) and updates the .mapinfo title.
Clean Backups – deletes .bak and .autosave files.
Pack it – builds a ready-to-play .pk3, optionally including the editable .map.
Create new map folder – sets up a project with the standard Xonotic subfolders.

Usage:
Requires Python 3.8+. Put mapping_helper.py next to your map project folders and run:  
```
python3 mapping_helper.py
```

Notes
- A project folder needs a maps/ subfolder containing your .map file.  
- Support packages are found automatically in your Xonotic data folder (file names containing mapping or extra). The folder can be changed in the settings.  
- Settings (export path, filename prefix, revision format, data folder, projects folder, include .map) are saved in mapping_helper_config.json next to the script.  
- Renaming and deleting always ask for confirmation. Texture export never overwrites existing files.  
- Shader scripts from the support packages are not copied; add them to your scripts/ folder if needed.  
- Developed on Linux; Windows and macOS paths are detected but less tested.

  
Disclaimer:  
- This python script is writtin entirely by claude.ai, im to stupit to do that myself.
