"""
src/content/
=============
Content management domain — notes, files, and search.

This layer sits between the service layer and the storage/tools layer.
It provides domain logic for:
  - ``SearchCoordinator`` — fan-out search across multiple backends
  - ``NoteManager``       — note CRUD + context assembly
  - ``FileManager``       — file read + context assembly

Phase 5 scope: basic implementations wired to existing repositories.
"""
