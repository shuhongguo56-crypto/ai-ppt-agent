import binascii
import struct
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def chunk(kind: bytes, payload: bytes = b"", *, crc: int | None = None) -> bytes:
    checksum = binascii.crc32(kind + payload) & 0xFFFFFFFF if crc is None else crc
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def ihdr(
    width: int = 2,
    height: int = 2,
    *,
    bit_depth: int = 8,
    color_type: int = 2,
    compression: int = 0,
    filter_method: int = 0,
    interlace: int = 0,
) -> bytes:
    return chunk(
        b"IHDR",
        struct.pack(
            ">IIBBBBB",
            width,
            height,
            bit_depth,
            color_type,
            compression,
            filter_method,
            interlace,
        ),
    )


def assemble(*chunks: bytes, signature: bytes = PNG_SIGNATURE, trailing: bytes = b"") -> bytes:
    return signature + b"".join(chunks) + trailing


def png(
    width: int = 2,
    height: int = 2,
    *,
    color_type: int = 2,
    filters: tuple[int, ...] | None = None,
    idat_parts: int = 1,
) -> bytes:
    bpp = 3 if color_type == 2 else 4
    row_filters = filters or (0,) * height
    raw = b"".join(bytes([row_filters[index]]) + bytes([index % 251]) * (width * bpp) for index in range(height))
    compressed = zlib.compress(raw)
    boundaries = [len(compressed) * i // idat_parts for i in range(idat_parts + 1)]
    idats = [chunk(b"IDAT", compressed[boundaries[i] : boundaries[i + 1]]) for i in range(idat_parts)]
    return assemble(ihdr(width, height, color_type=color_type), *idats, chunk(b"IEND"))
