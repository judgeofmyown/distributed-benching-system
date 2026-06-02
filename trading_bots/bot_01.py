import socket
import asyncio
import uuid
import threading
import time
import struct
from enum import IntEnum

SERVER_HOST = '127.0.0.1'
SERVER_PORT = 8888

class Action(IntEnum):
    BUY = 1
    SELL = 2
    CANCEL = 3

class Bot:
    def __init__(self, asset_initial_price: int):
        self.server_host = SERVER_HOST
        self.server_port = SERVER_PORT
        self.b_id = str(uuid.uuid4())
        self.client_id = None
        self.is_connected = False
        self.buys = 0
        self.sells = 0
        self.canceled = 0
        self.p_buy = 45
        self.p_sell = 45
        self.p_cancel = 10
        self.asset_price = asset_initial_price
        self.std = 0.3 
        self.order_ids = []

    async def listen_to_exchange(self, reader, writer):
        """listen to exchange server continusly until exited."""
        print(f"[+] Bot {self.b_id} started listening loop.")
        while True:
            try:

                line_bytes = await reader.readline()
                
                if not line_bytes:
                    print(f"\n[!] Bot {self.b_id}: Disconnected from the exchange server.")

                cleaned = line_bytes.decode('utf-8').strip()
                if not cleaned:
                    continue
                
                try:
                    msg = json.loads(cleaned)
                    # capture system time here to compare against server time, and find out latency
                    
                    if msg.get("Type") == "FILL":
                        print(f"\n[ALERT] ** EXECUTION FILL ** -> Traded {msg['size']} units @ ${msg['price']:.2f}")
                        continue

                    if msg.get("status") == "ACK":
                        self.order_ids.append(msg['order_id'])
                        print(f"\n[ACK] -> Order Accepted. Assigned ID: {msg['order_id']}")
                        continue
                        
                    if msg.get("status") == "CANCELED":
                        print(f"\n[ACK] -> Order {msg['order_id']} Canceled.")
                        continue
                except json.JSONDecodeError:
                    pass

            except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
                print(f"[-] Bot {self.b_id}: Error listening to Exchange server!") 
                break
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
    
    def encode_order(action: Action, order_id: int|None, size: int|None, price: float|None) -> bytes:
        """fixed length binary encoding"""
        if order_id == None:
            # B, i, f
            format_spec = '!Bif'
            return struct.pack(format_spec, action.value, size, price)
        else:
            # B, i
            format_spec = '!Bi'
            return struct.pack(format_spec, action.value, order_id)

    def order_action(self):
        """" Decides its action"""
        
        action = ""

        if self.order_ids:
            action = random.choices(
                        ["BUY", "SELL", "CANCEL"],
                        weights=[self.p_buy, self.p_sell, self.p_cancel],
                        k=1
                    )[0]
        else:
            action = random.choices( 
                        ["BUY", "SELL"],
                        weights=[self.p_buy, self.p_sell],
                        k=1
                    )[0]

        if action in ["BUY", "SELL"]:        
            size = max(1, round(random.gauss(50, 20)))
            price = max(0.01, round(random.gauss(self.asset_price, self.std), 2))
            return action, size, price
        else:
            order_id_to_cancel = random.randint(0, len(self.order_ids)-1)
            order_id = self.order_ids[order_id_to_cancel]
            self.order_ids.remove(order_id)
            return action, order_id 

     
    def strategy_coroutine(self, writer):
        """Wait for some time, take action, order blast."""
        
        while self.is_connected:
            # wait for some time
            await asyncio.sleep(2)
            command = self.order_action()
            
            if len(command) == 3:
                # BUY/SELL
                action, size, price = command
                if action == Action.BUY.name:
                    self.buys+=1
                    order_bin_packet = encode_order(Action.BUY, size=size, price=price)
                else:
                    self.sells+=1
                    order_bin_packet = encode_order(Action.SELL, size=size, price=price)     
                
            else:
                # CANCEL
                action, order_id = command
                self.canceled+=1

                order_bin_packet = encode_order(Action.CANCEL, order_id=order_id)
            
            # write to the server commands
            writer.write(order_bin_packet)
            await writer.drain()

    async def start(self):
        """connects to exchange server"""
        reader, writer = await asyncio.open_connection(
                    self.server_host,
                    self.server_port
                )

        self.is_connected = True
        local_port = writer.get_extra_info('peername')[1]
        self.client_id = f"CLIENT_{local_port}"
        print(f"[+] Connected to Exchange! Assigned Identifier: {self.client_id}")

        self.listen_task = asyncio.create_task(self.listen_to_exchange(reader, writer))
        self.strategy_task = asyncio.create_task(self.strategy_coroutine(writer))






