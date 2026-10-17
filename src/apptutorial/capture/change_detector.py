"""Local screen-change detection (perceptual hash / frame diff + debounce).

Gates the expensive vision verification call so frames are never streamed continuously
to the API. Implemented in M5. See SPEC.md §6.
"""
