import asyncio
import json
from Orderbook import OrderBook, Side, LimitOrder, MarketOrder, CancelOrder

class ExchangeServer:
    def __init__(self, host='127.0.0.1', port=8888):
        self.host = host
        self.port = port
        self.order_book = OrderBook()
        self.order_id_counter = 0
        self.client_registry = {}
        self.connected_clients = set()


    async def broadcast(self, message: dict):
        """Broadcasts market state updates to all active connection feeds."""
        payload = (json.dumps(message) + "\n").encode('utf-8')
        if self.connected_clients:
            await asyncio.gather(
                *[client.write(payload) or client.drain() for client in self.connected_clients],
                return_exceptions=True
            )

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Manages an individual client connection loop."""
        self.connected_clients.add(writer)
        peer = writer.get_extra_info('peername')
        client_id = f"CLIENT_{peer[1]}"
        self.client_registry[client_id] = writer
#        print(f"[*] Gateway opened for client connection: {peer}")

        try:
            while True:
                data = await reader.readline()
                if not data:
                    break # Client disconnected safely

                raw_msg = data.decode('utf-8').strip()
                if not raw_msg:
                    continue

                try:
                    payload = json.loads(raw_msg)
                    action = payload.get("action")
                    
                    # Core Routing Layer
                    if action in ("BUY", "SELL"):
                        self.order_id_counter += 1
                        order = LimitOrder(
                            order_id=self.order_id_counter,
                            side=Side.BUY if action == "BUY" else Side.SELL,
                            size=int(payload["size"]),
                            price=int(payload["price"])
                        )
                        order.client_id = client_id
                        # Process matching engine mutations
                        fills = self.order_book.process_order(order)
                        
                        print(self.order_book)

                        # Respond with order confirmation ID
                        response = {"status": "ACK", "order_id": self.order_id_counter}
                        writer.write((json.dumps(response) + "\n").encode('utf-8'))

                        for fill in fills:
                            fill_message = {
                                    "type": "FILL",
                                    "price": fill["price"],
                                    "size": fill["size"]
                            }
                            payload = (json.dumps(fill_message) + "\n").encode('utf-8')

                            incoming_writer = self.client_registry.get(fill["incoming_client"])
                            if incoming_writer:
                                incoming_writer.write(payload)

                                #if incoming_writer != writer:
                                await incoming_writer.drain()

                            book_writer = self.client_registry.get(fill["book_client"])
                            if book_writer:
                                book_writer.write(payload)
                                #if book_writer != writer:
                                await book_writer.drain()

                        await writer.drain()

                    elif action == "CANCEL":
                        order = CancelOrder(order_id=int(payload["order_id"]))
                        self.order_book.process_order(order)
                        
                        response = {"status": "CANCELED", "order_id": payload["order_id"]}
                        writer.write((json.dumps(response) + "\n").encode('utf-8'))
                        await writer.drain()

                    # Broadcast the new consolidated Order Book Depth matrix to everyone
                    await self.broadcast({
                        "type": "MD_UPDATE",
                        "best_bid": self.order_book.get_bid(),
                        "best_ask": self.order_book.get_ask(),
                        "total_resting": len(self.order_book)
                    })

                except Exception as parse_error:
                    error_resp = {"status": "REJECTED", "reason": str(parse_error)}
                    writer.write((json.dumps(error_resp) + "\n").encode('utf-8'))
                    await writer.drain()

        except asyncio.CancelledError:
            pass
        finally:
            self.connected_clients.remove(writer)
            self.client_registry.pop(client_id, None)
            writer.close()
            await writer.wait_closed()
            print(f"[-] Gateway closed for client connection: {peer}")

    async def start(self):
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        print(f"[+] Matching Engine active on TCP://{self.host}:{self.port}")
        async with server:
            await server.serve_forever()

if __name__ == "__main__":
    server = ExchangeServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n[!] Shutting down server engine.")
