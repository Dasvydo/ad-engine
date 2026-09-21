# Manual sweeps

Hand-collected competitor data — Ad Library reads done through the UI or the
MCP connector, before `META_ACCESS_TOKEN` existed.

**This is not `research/corpus/`.** That directory holds records the discovery
pipeline writes, each carrying a `schema` key and an id, and `engine/corpus.py`
refuses anything else. `tests/test_walk.py` asserts it contains nothing but
`.gitkeep` until the pipeline fills it. A hand-written file placed there breaks
the corpus loader for every reader.

Files here are dated, provenance-stamped, and free-form on purpose. Nothing
loads them automatically.
