import ctypes
from ctypes import c_void_p, c_char_p, POINTER, byref
import json
import os
import ctypes

# locate shared lib: allow override via env
env_path = os.environ.get("LIBMYDB_PATH")
if env_path:
    LIB_PATH = os.path.abspath(env_path)
else:
    LIB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bin", "libmydb.so"))

if not os.path.isfile(LIB_PATH):
    raise FileNotFoundError(f"Library not found at {LIB_PATH}. Build it or set LIBMYDB_PATH.")

_lib = ctypes.CDLL(LIB_PATH)

# function signatures
_lib.mydb_open.restype = c_void_p
_lib.mydb_open.argtypes = [c_char_p]

_lib.mydb_close.restype = None
_lib.mydb_close.argtypes = [c_void_p]

_lib.mydb_execute_json.restype = ctypes.c_int
_lib.mydb_execute_json.argtypes = [c_void_p, c_char_p, POINTER(c_char_p)]

# load libc for free()
_libc = None
for name in ("libc.so.6", "libc.dylib", None):
    try:
        if name:
            _libc = ctypes.CDLL(name)
        else:
            _libc = ctypes.CDLL(None)
        break
    except Exception:
        _libc = None
if _libc is None:
    raise RuntimeError("Unable to load C runtime to free memory")

_libc.free.argtypes = [c_void_p]
_libc.free.restype = None


class MyDB:
    """
    Simple wrapper around the C mydb library.
    Only provides execute(sql) and execute_json(sql).
    """
    def __init__(self, filename: str):
        if not filename:
            raise ValueError("filename required")
        self._h = _lib.mydb_open(filename.encode("utf-8"))
        if not self._h:
            raise RuntimeError(f"Failed to open DB: {filename}")

    def execute(self, sql: str):
        out = c_char_p()
        rc = _lib.mydb_execute_json(self._h, sql.encode("utf-8"), byref(out))
        text = None
        addr = ctypes.cast(out, c_void_p).value
        if addr:
            try:
                text = out.value.decode("utf-8")
            except Exception:
                text = out.value.decode("latin-1", "replace")
            # free the C-allocated buffer
            _libc.free(c_void_p(addr))
        return rc, text

    def execute_json(self, sql: str):
        rc, text = self.execute(sql)
        if text is None:
            return rc, None
        try:
            return rc, json.loads(text)
        except json.JSONDecodeError:
            return rc, text

    def close(self):
        if self._h:
            _lib.mydb_close(self._h)
            self._h = None


