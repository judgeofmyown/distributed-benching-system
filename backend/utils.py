import socket
import struct
import os
import sys

def parse_market_data_packet(data: bytes) -> dict | None:
    """Parses the new 17-byte header + dynamic payload protocol."""
    if len(data) < 17:
        return None

    # Unpack Header: !BQQ = 1 byte (uint8) + 8 bytes (uint64) + 8 bytes (uint64) in Network/Big-Endian
    msg_type_int, seq_num, timestamp = struct.unpack('!BQQ', data[:17])
    cursor = 17

    result = {
        "sequence": seq_num,
        "timestamp": timestamp,
    }

    if msg_type_int == 1:  # BOOK_SNAPSHOT
        result["type"] = "BOOK_SNAPSHOT"
        if len(data) < cursor + 2: return None
        
        num_bids, num_asks = struct.unpack('!BB', data[cursor:cursor+2])
        cursor += 2

        bids = []
        for _ in range(num_bids):
            # !fI = 4 byte float + 4 byte uint32
            price, qty = struct.unpack('!fI', data[cursor:cursor+8])
            bids.append({"price": round(price, 2), "qty": qty})
            cursor += 8

        asks = []
        for _ in range(num_asks):
            price, qty = struct.unpack('!fI', data[cursor:cursor+8])
            asks.append({"price": round(price, 2), "qty": qty})
            cursor += 8

        result["bids"] = bids
        result["asks"] = asks

    elif msg_type_int == 2:  # TRADE
        result["type"] = "TRADE"
        if len(data) < cursor + 12: return None
        
        # !IfI = 4 byte uint32 + 4 byte float + 4 byte uint32
        trade_id, price, qty = struct.unpack('!IfI', data[cursor:cursor+12])
        
        result["trade_id"] = trade_id
        result["price"] = round(price, 2)
        result["qty"] = qty
    else:
        return None

    return result