#-----------------------------------------------------------------------------
# Custom runtime hook for Access IRC
# Don't override GTK paths since we're using system GTK
#-----------------------------------------------------------------------------

def _pyi_rthook():
    import os
    # Don't set GTK_DATA_PREFIX, GTK_EXE_PREFIX, GTK_PATH
    # Let GTK use system paths instead
    pass

_pyi_rthook()
del _pyi_rthook
