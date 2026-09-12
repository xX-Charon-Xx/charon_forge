if not exist .\dist mkdir .\dist
blender --command extension build --source-dir .\src\addons\charon_forge\ --output-dir .\dist
