import os
import ctypes
import msgpack
from typing import Any
from platform import uname
from collections.abc import Generator

if uname().system == "Windows":
    LIB = ctypes.cdll.LoadLibrary(
        os.path.join(os.path.dirname(__file__), "libbdxbuilder_windows_amd64.dll")
    )
elif uname().system == "Linux":
    LIB = ctypes.cdll.LoadLibrary(
        os.path.join(os.path.dirname(__file__), "libbdxbuilder_linux_amd64.so")
    )


def py_bytes(bytes_pointer: ctypes.c_void_p | None, bytelen: int = -1):
    if bytes_pointer is None:
        return b""
    bs = ctypes.string_at(bytes_pointer, size=bytelen)
    LIB.Free(bytes_pointer)
    return bs


def py_string(str_pointer: ctypes.c_void_p | None):
    return py_bytes(str_pointer).decode(errors="ignore")


def c_string(s: str):
    return s.encode()


def check_panic(obj: ctypes.Structure):
    err_str = py_string(obj.err)
    if err_str != "":
        raise RuntimeError(err_str)


class BasicError(ctypes.Structure):
    err: ctypes.c_void_p
    _fields_ = (("err", ctypes.c_void_p),)


class BDXLen_return(ctypes.Structure):
    length: int
    err: ctypes.c_void_p
    _fields_ = (
        ("length", ctypes.c_int32),
        ("err", ctypes.c_void_p),
    )


class YieldCommand_return(ctypes.Structure):
    payload: ctypes.c_void_p
    payload_length: int
    is_eof: int
    err: ctypes.c_void_p
    _fields_ = (
        ("payload", ctypes.c_void_p),
        ("payload_length", ctypes.c_int32),
        ("is_eof", ctypes.c_int32),
        ("err", ctypes.c_void_p),
    )


LIB.LoadBDX.argtypes = (ctypes.c_char_p,)
LIB.LoadBDX.restype = BasicError
LIB.BDXTotalLen.argtypes = ()
LIB.BDXTotalLen.restype = BDXLen_return
LIB.BDXBlocks.argtypes = ()
LIB.BDXBlocks.restype = BDXLen_return
LIB.YieldCommand.argtypes = ()
LIB.YieldCommand.restype = YieldCommand_return
LIB.Free.argtypes = (ctypes.c_void_p,)


def Init():
    LIB.Init()


def LoadBDX(path: str) -> None:
    check_panic(LIB.LoadBDX(c_string(path)))


def BDXTotalLen() -> int:
    ret: BDXLen_return = LIB.BDXTotalLen()
    check_panic(ret)
    return ret.length


def BDXBlocks() -> int:
    ret: BDXLen_return = LIB.BDXBlocks()
    check_panic(ret)
    return ret.length


def YieldCommand() -> Generator[tuple[int, dict], Any, None]:
    while 1:
        ret: YieldCommand_return = LIB.YieldCommand()
        check_panic(ret)
        payload = py_bytes(ret.payload, ret.payload_length)
        is_eof = ret.is_eof
        err_str = py_string(ret.err)
        if is_eof:
            break
        elif err_str:
            raise RuntimeError(err_str)
        else:
            try:
                content = msgpack.unpackb(payload)
            except UnicodeDecodeError:
                content = RawParse(msgpack.unpackb(payload, raw=True))
            yield content["ID"], content["Data"]


def RawParse(raw) -> Any:
    if isinstance(raw, dict):
        new_dict = {}
        for k, v in raw.items():
            new_dict[_safe_decode(k)] = RawParse(v)
        return new_dict
    elif isinstance(raw, list):
        return [RawParse(v) for v in raw]
    elif isinstance(raw, bytes):
        return _safe_decode(raw)
    else:
        return raw


def _safe_decode(s: bytes):
    try:
        return s.decode()
    except UnicodeDecodeError:
        res = s.decode(errors="replace")
        print(f"忽略编码错误: {res}")
        return res
