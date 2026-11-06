"""Public preview storage: no files, secrets, databases or cross-session state."""
from copy import deepcopy


def load_item(state, key):
    return deepcopy(state.get("_preview_store", {}).get(key, {}))


def save_item(state, key, value):
    store = dict(state.get("_preview_store", {}))
    store[key] = deepcopy(value)
    state["_preview_store"] = store
