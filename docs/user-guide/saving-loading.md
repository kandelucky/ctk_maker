# Saving & Loading

> How projects are persisted and reloaded.

## File format

TODO: JSON with `"version": 1` field for forward migration.
Describe top-level keys (metadata, widgets tree, canvas settings).

## Saving

TODO: File → Save / Save As flow.
Source: [app/io/project_saver.py](../../app/io/project_saver.py).

## Loading

TODO: File → Open flow, version check, error handling.
Source: [app/io/project_loader.py](../../app/io/project_loader.py).

## Recent files

TODO: Where the recents list is stored and how it is pruned.
Source: [app/core/recent_files.py](../../app/core/recent_files.py).

## Migration policy

TODO: Rules for bumping the `version` field and how old files are upgraded.

## Example file

```json
{
  "version": 1,
  "...": "TODO: minimal example"
}
```
