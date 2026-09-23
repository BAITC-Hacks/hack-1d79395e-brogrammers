"""Validate graph selection without changing the 18-digit account identifier."""

def selected_gid(event, available):
    selection = event.get("selection", {})
    allowed = set(map(str, available))
    for point in selection.get("points", []):
        custom = point.get("customdata")
        if isinstance(custom, (list, tuple)) and custom:
            gid = custom[0]
            # Only the exact string emitted by the graph is accepted. Floats
            # have already lost precision for 18-digit account identifiers.
            if isinstance(gid, str) and gid in allowed:
                return gid
    return None
