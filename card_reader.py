import ctypes
import platform
import time
from pathlib import Path


# =========================================================
# rf IDEAS SDK path
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

SDK_DIR = (
    BASE_DIR
    / "pcProxAPI-7.10.1-Windows"
)


if ctypes.sizeof(ctypes.c_void_p) == 8:

    DLL_PATH = (
        SDK_DIR
        / "lib"
        / "64"
        / "pcProxAPI.dll"
    )

else:

    DLL_PATH = (
        SDK_DIR
        / "lib"
        / "32"
        / "pcProxAPI.dll"
    )


# =========================================================
# DLL
# =========================================================

_pcproxlib = None


def load_library():

    global _pcproxlib

    if _pcproxlib is not None:
        return _pcproxlib

    if platform.system() != "Windows":

        raise RuntimeError(
            "rf IDEAS reader integration "
            "currently requires Windows."
        )

    if not DLL_PATH.exists():

        raise FileNotFoundError(
            f"pcProxAPI.dll was not found at:\n"
            f"{DLL_PATH}"
        )

    _pcproxlib = ctypes.WinDLL(
        str(DLL_PATH)
    )

    # Search USB devices only
    _pcproxlib.SetDevTypeSrch.restype = (
        ctypes.c_short
    )

    _pcproxlib.SetDevTypeSrch(
        ctypes.c_short(0)
    )

    return _pcproxlib


# =========================================================
# Connect
# =========================================================

def connect_reader():

    lib = load_library()

    lib.usbConnect.restype = (
        ctypes.c_short
    )

    result = lib.usbConnect()

    if result == 1:

        # Give the reader a short time
        # to become ready after connection
        time.sleep(0.25)

        return True

    return False


def disconnect_reader():

    global _pcproxlib

    if _pcproxlib is None:
        return

    try:

        _pcproxlib.USBDisconnect.restype = (
            ctypes.c_short
        )

        _pcproxlib.USBDisconnect()

    except Exception:
        pass


# =========================================================
# Reader information
# =========================================================

def get_reader_count():

    lib = load_library()

    lib.GetDevCnt.restype = (
        ctypes.c_short
    )

    return int(
        lib.GetDevCnt()
    )


def get_reader_name():

    lib = load_library()

    lib.getPartNumberString.restype = (
        ctypes.POINTER(
            ctypes.c_char
        )
    )

    ptr = (
        lib.getPartNumberString()
    )

    if not ptr:
        return None

    return (
        ctypes.string_at(ptr)
        .decode(
            "utf-8",
            errors="ignore"
        )
    )


# =========================================================
# Card reading
# =========================================================

def read_card():

    """
    Read the card currently placed on the reader.

    Returns None if no card is detected.
    """

    lib = load_library()

    buffer_size = (
        ctypes.c_short(32)
    )

    raw_buffer = (
        ctypes.c_ubyte
        * buffer_size.value
    )()

    lib.GetActiveID32.restype = (
        ctypes.c_short
    )

    # IMPORTANT:
    # rf IDEAS official example requires
    # approximately 250 ms before GetActiveID32
    time.sleep(0.25)

    n_bits = (
        lib.GetActiveID32(
            raw_buffer,
            buffer_size
        )
    )

    if n_bits <= 0:
        return None


    bytes_to_read = int(
        (n_bits + 7) / 8
    )


    # Official example returns at least 8 bytes
    if bytes_to_read < 8:
        bytes_to_read = 8


    # Official rf IDEAS example prints
    # the bytes in reverse order
    raw_bytes = [

        raw_buffer[i]

        for i in range(
            bytes_to_read - 1,
            -1,
            -1
        )

    ]


    raw_string = " ".join(

        f"{value:02X}"

        for value in raw_bytes

    )


    card_id = "".join(

        f"{value:02X}"

        for value in raw_bytes

    )


    return {

        "bits":
            int(n_bits),

        "raw":
            raw_string,

        "card_id":
            card_id,

    }


# =========================================================
# Standalone test
# =========================================================

if __name__ == "__main__":

    print(
        "rf IDEAS Card Reader Test"
    )

    print(
        f"DLL: {DLL_PATH}"
    )

    try:

        if not connect_reader():

            print(
                "Reader not connected."
            )

        else:

            print(
                "Reader connected."
            )

            print(
                f"Reader: "
                f"{get_reader_name()}"
            )

            print(
                "Place the card on the reader."
            )

            input(
                "Press Enter when ready: "
            )

            card = read_card()

            if card is None:

                print(
                    "No card detected."
                )

            else:

                print(
                    f"Bits: "
                    f"{card['bits']}"
                )

                print(
                    f"Raw: "
                    f"{card['raw']}"
                )

                print(
                    f"Card ID: "
                    f"{card['card_id']}"
                )

    finally:

        disconnect_reader()