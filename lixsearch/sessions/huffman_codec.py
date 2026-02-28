"""
Pure Huffman codec for conversation compression.
Optimized for speed - canonical Huffman with bit-level streaming.
No external dependencies beyond stdlib.
"""
import heapq
import struct
from typing import Dict, Tuple, Optional


class _HNode:
    __slots__ = ("freq", "sym", "left", "right")

    def __init__(self, freq: int, sym: Optional[int], left=None, right=None):
        self.freq = freq
        self.sym = sym
        self.left = left
        self.right = right

    def __lt__(self, other: "_HNode") -> bool:
        return self.freq < other.freq


def _build_tree(data: bytes) -> Optional["_HNode"]:
    freq: Dict[int, int] = {}
    for b in data:
        freq[b] = freq.get(b, 0) + 1

    heap = [_HNode(f, s) for s, f in freq.items()]
    heapq.heapify(heap)

    if len(heap) == 1:
        # Single symbol edge-case: wrap in a parent
        n = heap[0]
        heapq.heappush(heap, _HNode(n.freq, None, n, _HNode(0, n.sym)))

    while len(heap) > 1:
        a = heapq.heappop(heap)
        b = heapq.heappop(heap)
        heapq.heappush(heap, _HNode(a.freq + b.freq, None, a, b))

    return heap[0] if heap else None


def _build_codes(node: Optional["_HNode"], prefix: int = 0, length: int = 0, codes: Dict[int, Tuple[int, int]] = None) -> Dict[int, Tuple[int, int]]:
    """Returns {symbol: (code_int, bit_length)} for each leaf."""
    if codes is None:
        codes = {}
    if node is None:
        return codes
    if node.sym is not None:
        codes[node.sym] = (prefix, length)
    else:
        _build_codes(node.left, prefix << 1, length + 1, codes)
        _build_codes(node.right, (prefix << 1) | 1, length + 1, codes)
    return codes


class HuffmanCodec:
    """
    Pure-python Huffman encoder/decoder.
    Wire format:
        [4B] original_length (uint32 LE)
        [2B] num_symbols (uint16 LE)
        for each symbol:
            [1B] symbol byte value
            [1B] code bit-length
        [4B] padding_bits (uint32 LE)  – bits padded at end
        [N B] compressed bitstream (MSB-first)
    """

    MAGIC = b"HCv1"

    @staticmethod
    def encode(data: bytes) -> bytes:
        if not data:
            return HuffmanCodec.MAGIC + struct.pack("<I", 0) + b"\x00\x00"

        tree = _build_tree(data)
        if tree is None:
            return HuffmanCodec.MAGIC + struct.pack("<I", 0) + b"\x00\x00"

        codes = _build_codes(tree)

        # Build bitstream
        bit_buf = 0
        bit_len = 0
        out_bytes = bytearray()

        for b in data:
            code, length = codes[b]
            bit_buf = (bit_buf << length) | code
            bit_len += length
            while bit_len >= 8:
                bit_len -= 8
                out_bytes.append((bit_buf >> bit_len) & 0xFF)

        padding = 0
        if bit_len > 0:
            padding = 8 - bit_len
            out_bytes.append((bit_buf << padding) & 0xFF)

        # Build header
        syms = sorted(codes.keys())
        num_symbols = len(syms)
        header = bytearray()
        header += HuffmanCodec.MAGIC
        header += struct.pack("<I", len(data))       # original length
        header += struct.pack("<H", num_symbols)     # symbol count
        for sym in syms:
            _, length = codes[sym]
            header += bytes([sym, length])
        header += struct.pack("<I", padding)         # padding bits

        return bytes(header) + bytes(out_bytes)

    @staticmethod
    def decode(data: bytes) -> bytes:
        if not data:
            return b""

        offset = 0
        magic = data[offset:offset + 4]
        offset += 4
        if magic != HuffmanCodec.MAGIC:
            raise ValueError(f"Invalid Huffman magic: {magic!r}")

        orig_len = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        if orig_len == 0:
            return b""

        num_symbols = struct.unpack_from("<H", data, offset)[0]
        offset += 2

        sym_lengths: list[Tuple[int, int]] = []
        for _ in range(num_symbols):
            sym = data[offset]
            length = data[offset + 1]
            sym_lengths.append((sym, length))
            offset += 2

        padding = struct.unpack_from("<I", data, offset)[0]
        offset += 4

        compressed = data[offset:]

        # Rebuild canonical codes from (sym, length) pairs
        # Sort by (length, symbol) for canonical ordering
        sym_lengths.sort(key=lambda x: (x[1], x[0]))

        # Assign canonical codes
        decode_table: Dict[Tuple[int, int], int] = {}
        canon_code = 0
        prev_len = 0
        for sym, length in sym_lengths:
            if length > prev_len:
                canon_code <<= (length - prev_len)
                prev_len = length
            decode_table[(canon_code, length)] = sym
            canon_code += 1

        # Decode bitstream
        result = bytearray()
        bit_buf = 0
        bit_len = 0
        code_acc = 0
        code_len = 0
        total_bits = len(compressed) * 8 - padding

        bit_pos = 0
        byte_idx = 0
        bit_in_byte = 7

        for _ in range(total_bits):
            bit = (compressed[byte_idx] >> bit_in_byte) & 1
            code_acc = (code_acc << 1) | bit
            code_len += 1
            bit_in_byte -= 1
            if bit_in_byte < 0:
                bit_in_byte = 7
                byte_idx += 1

            key = (code_acc, code_len)
            if key in decode_table:
                result.append(decode_table[key])
                code_acc = 0
                code_len = 0
                if len(result) >= orig_len:
                    break

        return bytes(result)


def encode_str(text: str) -> bytes:
    """Encode a UTF-8 string to Huffman-compressed bytes."""
    return HuffmanCodec.encode(text.encode("utf-8"))


def decode_bytes(data: bytes) -> str:
    """Decode Huffman-compressed bytes back to a UTF-8 string."""
    return HuffmanCodec.decode(data).decode("utf-8")
