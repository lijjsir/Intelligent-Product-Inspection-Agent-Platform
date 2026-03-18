from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    ms = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(10), "big")
    # 48 bits timestamp, 12 bits rand, 62 bits rand
    uuid_int = (ms & ((1 << 48) - 1)) << 80
    uuid_int |= (rand & ((1 << 80) - 1))
    # set version 7 (0b0111) and variant 10xx
    uuid_int &= ~(0xF << 76)
    uuid_int |= 0x7 << 76
    uuid_int &= ~(0x3 << 62)
    uuid_int |= 0x2 << 62
    return uuid.UUID(int=uuid_int)
