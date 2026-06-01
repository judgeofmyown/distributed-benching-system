from order import *
from Trade import *
from sortedcontainers import SortedList

class OrderBook(object):

    def __init__(self):
        self.bids: SortedList[Order] = SortedList() 
        self.asks: SortedList[Order] = SortedList()
        self.trades = []
        
        self.total_trades_count = 0    # Tracks total number of trade events
        self.total_volume_traded = 0   # Tracks cumulative size traded
        self.total_value_traded = 0.0  # Tracks cumulative dollar value (Price * Size)

    def process_order(self, incoming_order):
        executed_fills = []

        if incoming_order.__class__ == CancelOrder:
            for order in self.bids:
                if incoming_order.order_id == order.order_id:
                    self.bids.discard(order)
                    break

            for order in self.asks:
                if incoming_order.order_id == order.order_id:
                    self.asks.discard(order)
                    break
            
            return # Exiting process order

        def while_clause():
            """
            Determined whether to continue the while-loop
            """
            if incoming_order.side==Side.BUY:
                if incoming_order.__class__ == LimitOrder:
                    return len(self.asks) > 0 and incoming_order.price >= self.asks[0].price # Limit order on the BUY side
                elif incoming_order.__class__ == MarketOrder:
                    return len(self.asks) > 0 # Market order on the BUY side
            else:
                if incoming_order.__class__ == LimitOrder:
                    return len(self.bids) > 0 and incoming_order.price <= self.bids[0].price # Limit order on the SELL side
                elif incoming_order.__class__ == MarketOrder:
                    return len(self.bids) > 0 # Market order on the SELL side

        # while there are orders and the orders requirements are matched
        while while_clause():
            bookOrder = None
            if incoming_order.side==Side.BUY:
                bookOrder = self.asks.pop(0)
            else:
                bookOrder = self.bids.pop(0)

            volume = min(incoming_order.remaining, bookOrder.remaining)

            self.total_trades_count += 1
            self.total_volume_traded += volume
            self.total_value_traded += (bookOrder.price * volume)

            if incoming_order.remaining == bookOrder.remaining:  # if the same volume
                volume = incoming_order.remaining
                incoming_order.remaining -= volume
                bookOrder.remaining -= volume
                self.trades.append(Trade(
                    incoming_order.side, bookOrder.price, volume, incoming_order.order_id, bookOrder.order_id))
                fill_info = {
                    "incoming_client": incoming_order.client_id,
                    "book_client": bookOrder.client_id,
                    "price": bookOrder.price,
                    "size": volume
                }
                executed_fills.append(fill_info) 
                break

            elif incoming_order.remaining > bookOrder.remaining:  # incoming has greater volume
                volume = bookOrder.remaining
                incoming_order.remaining -= volume
                bookOrder.remaining -= volume
                self.trades.append(Trade(
                    incoming_order.side, bookOrder.price, volume, incoming_order.order_id, bookOrder.order_id))
                 
                fill_info = {
                    "incoming_client": incoming_order.client_id,
                    "book_client": bookOrder.client_id,
                    "price": bookOrder.price,
                    "size": volume
                } 
                executed_fills.append(fill_info) 

            elif incoming_order.remaining < bookOrder.remaining:  # book has greater volume
                volume = incoming_order.remaining
                incoming_order.remaining -= volume
                bookOrder.remaining -= volume
                self.trades.append(Trade(
                    incoming_order.side, bookOrder.price, volume, incoming_order.order_id, bookOrder.order_id))
                
                fill_info = {
                    "incoming_client": incoming_order.client_id,
                    "book_client": bookOrder.client_id,
                    "price": bookOrder.price,
                    "size": volume
                }
                executed_fills.append(fill_info) 
                if bookOrder.side==Side.SELL:
                    self.asks.add(bookOrder)
                else:
                    self.bids.add(bookOrder)
                break

        if incoming_order.remaining > 0 and incoming_order.__class__ == LimitOrder:
            if incoming_order.side == Side.BUY:
                self.bids.add(incoming_order)
            else:
                self.asks.add(incoming_order)

        return executed_fills
        
    def get_bid(self): return self.bids[0].price if len(self.bids)>0 else None
    def get_ask(self): return self.asks[0].price if len(self.asks)>0 else None

    def __repr__(self):
        ask_depth = {}
        for order in self.asks:
            ask_depth[order.price] = ask_depth.get(order.price, 0) + order.remaining

        # 2. Aggregate Bids
        bid_depth = {}
        for order in self.bids:
            bid_depth[order.price] = bid_depth.get(order.price, 0) + order.remaining
       
        if self.total_volume_traded > 0:
            avg_price = self.total_value_traded/self.total_volume_traded
        else:
            avg_price = 0.0

        # 3. Format the Self-Refreshing Table Frame
        lines = []
        
        # \033[2J clears the screen; \033[H snaps the cursor back to row 0, col 0
        lines.append("\033[2J\033[H") 
        lines.append("="*35)
        lines.append(f"{'BID SIZE':<12} | {'PRICE':^7} | {'ASK SIZE':>12}")
        lines.append("-"*35)

        # Print Asks from highest price down to lowest (Sell orders on top)
        for price in sorted(ask_depth.keys(), reverse=True):
            lines.append(f"{'':<12} | {price:^7.2f} | {ask_depth[price]:>12}")

        lines.append("-"*35) # The Spread Divide Line

        # Print Bids from highest price down to lowest (Buy orders on bottom)
        for price in sorted(bid_depth.keys(), reverse=True):
            lines.append(f"{bid_depth[price]:<12} | {price:^7.2f} | {'':>12}")

        lines.append("="*35)
        
        lines.append(f" Total Trades Triggered : {self.total_trades_count}")
        lines.append(f" Total Volume Traded    : {self.total_volume_traded}")
        lines.append(f" Avg Execution Price    : ${avg_price:.2f}")
        lines.append("="*35)
        
        return "\n".join(lines)
    
    def __len__(self):
        return len(self.asks) + len(self.bids)
    
