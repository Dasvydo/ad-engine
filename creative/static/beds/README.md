# Bed prompts

The `hm-static-ad-generator` skill defaults to **hybrid** mode: an LLM-image
model generates the *bed* (background, imagery, product realism), and the
brand-critical layer is typeset over it in the Playwright pipeline. No image
model is available in this session, so the eight creatives currently ship as
typeset-only layouts on solid brand grounds, which the brand lock allows.

These are the eight bed prompts, written to the skill's Mode A scaffold with the
constraint block on every one. To use them:

1. Run a prompt through Nano Banana Pro (or Seedream, GPT Image, Imagen).
2. Save the result as `creative/static/beds/<creative-id>.png`.
3. Re-run `python -m creative.static.render all`.

The renderer already looks for `beds/<id>.png` and draws it behind the type. No
code change is needed. Re-run `python -m creative.static.vet` afterwards, because
a bed is the fastest way to break the amber rule and the background rule at once.

Every prompt leaves the type zone deliberately clear, because the headline,
the wordmark and the single amber accent are typeset, not generated.
