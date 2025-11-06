# nuvix_patch.py — Fix for Render/Python >=3.12 where 'audioop' may be missing.
# We provide a minimal shim so discord.py doesn't crash on import.
import sys, types
if "audioop" not in sys.modules:
    sys.modules["audioop"] = types.SimpleNamespace(
        add=lambda *a, **kw: None,
        mul=lambda *a, **kw: None,
        bias=lambda *a, **kw: None,
        avg=lambda *a, **kw: 0,
        max=lambda *a, **kw: 0,
        minmax=lambda *a, **kw: (0, 0),
        rms=lambda *a, **kw: 0,
        cross=lambda *a, **kw: 0,
        reverse=lambda *a, **kw: b"",
        tostereo=lambda *a, **kw: b"",
        tomono=lambda *a, **kw: b"",
    )
