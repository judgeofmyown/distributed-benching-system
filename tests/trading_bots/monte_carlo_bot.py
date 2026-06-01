from Orderbook import *
from random import getrandbits, randint

def main():

    order_book = OrderBook()
    orders = []
    order_counts = 200
    for i in range(order_counts):
        if bool(getrandbits(1)):
            orders.append(LimitOrder(i, Side.BUY, randint(1, 200), randint(1, 10)))
        else:
            orders.append(LimitOrder(i, Side.SELL, randint(1, 200), randint(1, 10)))
    
    from time import time
    start = time()
    for order in orders:
        order_book.process_order(order)
    print(order_book)
    end = time()

    totaltime = end - start

    print("Time: " + str(totaltime))
    print("Time per order (us): " + str(1000000*totaltime/order_counts))
    # print("Orders per second: " + str(order_counts/totaltime))
    
main()

