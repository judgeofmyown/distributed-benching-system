#include <iostream>
#include <vector>
#include <map>
#include <unordered_map>
#include <memory>
#include <string>
#include <cstring>
#include <chrono>
#include <thread>
#include <algorithm>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>

// --- Network Byte Ordering Utilities ---
// Mapping python's float struct formatting 'f' (32-bit float) and 'q' (64-bit int)
uint64_t htonll(uint64_t val) {
    #if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    return (((uint64_t)htonl(val & 0xFFFFFFFF)) << 32) | htonl(val >> 32);
    #else
    return val;
    #endif
}

float ntohf(float val) {
    uint32_t temp;
    std::memcpy(&temp, &val, 4);
    temp = ntohl(temp);
    std::memcpy(&val, &temp, 4);
    return val;
}

// --- Enum Protocols ---
enum class Action : uint8_t {
    BUY = 1,
    SELL = 2,
    CANCEL = 3,
    MARKET_BUY = 4,
    MARKET_SELL = 5
};

enum class ServerMsg : uint8_t {
    ACK = 10,
    FILL = 15,
    REJECT = 30
};

// --- Order & Data Structures ---
struct Order {
    uint32_t order_id;
    uint32_t client_req_id;
    int client_fd;
    uint32_t qty;
    float price;
    bool is_buy;
};

// Custom comparators for the Order Book Price levels
struct AskComp { bool operator()(const float& a, const float& b) const { return a < b; } }; // Lowest ask first
struct BidComp { bool operator()(const float& a, const float& b) const { return a > b; } }; // Highest bid first

class OrderBook {
private:
    uint32_t next_order_id = 1;
    
    // Price -> List of Orders at that price level
    std::map<float, std::vector<std::shared_ptr<Order>>, BidComp> bids;
    std::map<float, std::vector<std::shared_ptr<Order>>, AskComp> asks;
    
    // Quick lookup for cancels
    std::unordered_map<uint32_t, std::shared_ptr<Order>> active_orders;

    void send_packet(int client_fd, const std::vector<uint8_t>& packet) {
        uint8_t len = packet.size();
        send(client_fd, &len, 1, 0); // Write length prefix byte
        send(client_fd, packet.data(), len, 0);
    }

public:
    void send_ack(int client_fd, uint32_t client_req_id, uint32_t order_id, int64_t t_recv) {
        // Struct format: '!Biiqq' -> 1 + 4 + 4 + 8 + 8 = 25 Bytes
        std::vector<uint8_t> buffer(25);
        int64_t t_send = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::high_resolution_clock::now().time_since_epoch()).count();
        
        uint8_t msg_type = static_cast<uint8_t>(ServerMsg::ACK);
        uint32_t r_id = htonl(client_req_id);
        uint32_t o_id = htonl(order_id);
        int64_t tr = htonll(t_recv);
        int64_t ts = htonll(t_send);

        std::memcpy(&buffer[0], &msg_type, 1);
        std::memcpy(&buffer[1], &r_id, 4);
        std::memcpy(&buffer[5], &o_id, 4);
        std::memcpy(&buffer[9], &tr, 8);
        std::memcpy(&buffer[17], &ts, 8);

        send_packet(client_fd, buffer);
    }

    void send_fill(int client_fd, uint32_t client_req_id, uint32_t order_id, uint32_t fill_qty, float exec_price, int64_t t_recv) {
        // Struct format: '!Biiifqq' -> 1 + 4 + 4 + 4 + 4 + 8 + 8 = 33 Bytes
        std::vector<uint8_t> buffer(33);
        int64_t t_send = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::high_resolution_clock::now().time_since_epoch()).count();

        uint8_t msg_type = static_cast<uint8_t>(ServerMsg::FILL);
        uint32_t r_id = htonl(client_req_id);
        uint32_t o_id = htonl(order_id);
        uint32_t f_qty = htonl(fill_qty);
        
        uint32_t price_bin;
        std::memcpy(&price_bin, &exec_price, 4);
        price_bin = htonl(price_bin);

        int64_t tr = htonll(t_recv);
        int64_t ts = htonll(t_send);

        std::memcpy(&buffer[0], &msg_type, 1);
        std::memcpy(&buffer[1], &r_id, 4);
        std::memcpy(&buffer[5], &o_id, 4);
        std::memcpy(&buffer[9], &f_qty, 4);
        std::memcpy(&buffer[13], &price_bin, 4);
        std::memcpy(&buffer[17], &tr, 8);
        std::memcpy(&buffer[25], &ts, 8);

        send_packet(client_fd, buffer);
    }

    void send_reject(int client_fd, uint32_t client_req_id, uint32_t order_id, uint8_t error_code) {
        // Bot expectation mismatch workaround: Bot reads length 10 as '!BiiB' (1 + 4 + 4 + 1)
        std::vector<uint8_t> buffer(10);
        uint8_t msg_type = static_cast<uint8_t>(ServerMsg::REJECT);
        uint32_t r_id = htonl(client_req_id);
        uint32_t o_id = htonl(order_id);

        std::memcpy(&buffer[0], &msg_type, 1);
        std::memcpy(&buffer[1], &r_id, 4);
        std::memcpy(&buffer[5], &o_id, 4);
        std::memcpy(&buffer[9], &error_code, 1);

        send_packet(client_fd, buffer);
    }

    void process_limit_order(uint32_t client_req_id, int client_fd, uint32_t qty, float price, bool is_buy, int64_t t_recv) {
        uint32_t order_id = next_order_id++;
        
        // Instant ACK back to bot
        send_ack(client_fd, client_req_id, order_id, t_recv);

        // Matching Engine Execution logic
        if (is_buy) {
            while (qty > 0 && !asks.empty() && asks.begin()->first <= price) {
                auto& order_list = asks.begin()->second;
                while (!order_list.empty() && qty > 0) {
                    auto match_order = order_list.front();
                    uint32_t fill = std::min(qty, match_order->qty);

                    qty -= fill;
                    match_order->qty -= fill;

                    // Send fills to both participants
                    send_fill(client_fd, client_req_id, order_id, fill, match_order->price, t_recv);
                    send_fill(match_order->client_fd, match_order->client_req_id, match_order->order_id, fill, match_order->price, t_recv);

                    if (match_order->qty == 0) {
                        active_orders.erase(match_order->order_id);
                        order_list.erase(order_list.begin());
                    }
                }
                if (order_list.empty()) asks.erase(asks.begin());
            }

            if (qty > 0) {
                auto new_order = std::make_shared<Order>(Order{order_id, client_req_id, client_fd, qty, price, true});
                bids[price].push_back(new_order);
                active_orders[order_id] = new_order;
            }
        } else { // SELL Order logic
            while (qty > 0 && !bids.empty() && bids.begin()->first >= price) {
                auto& order_list = bids.begin()->second;
                while (!order_list.empty() && qty > 0) {
                    auto match_order = order_list.front();
                    uint32_t fill = std::min(qty, match_order->qty);

                    qty -= fill;
                    match_order->qty -= fill;

                    send_fill(client_fd, client_req_id, order_id, fill, match_order->price, t_recv);
                    send_fill(match_order->client_fd, match_order->client_req_id, match_order->order_id, fill, match_order->price, t_recv);

                    if (match_order->qty == 0) {
                        active_orders.erase(match_order->order_id);
                        order_list.erase(order_list.begin());
                    }
                }
                if (order_list.empty()) bids.erase(bids.begin());
            }

            if (qty > 0) {
                auto new_order = std::make_shared<Order>(Order{order_id, client_req_id, client_fd, qty, price, false});
                asks[price].push_back(new_order);
                active_orders[order_id] = new_order;
            }
        }
    }

    void process_market_order(uint32_t client_req_id, int client_fd, uint32_t qty, bool is_buy, int64_t t_recv) {
        uint32_t order_id = next_order_id++;
        send_ack(client_fd, client_req_id, order_id, t_recv);

        if (is_buy) {
            while (qty > 0 && !asks.empty()) {
                auto& order_list = asks.begin()->second;
                while (!order_list.empty() && qty > 0) {
                    auto match_order = order_list.front();
                    uint32_t fill = std::min(qty, match_order->qty);
                    qty -= fill;
                    match_order->qty -= fill;

                    send_fill(client_fd, client_req_id, order_id, fill, match_order->price, t_recv);
                    send_fill(match_order->client_fd, match_order->client_req_id, match_order->order_id, fill, match_order->price, t_recv);

                    if (match_order->qty == 0) {
                        active_orders.erase(match_order->order_id);
                        order_list.erase(order_list.begin());
                    }
                }
                if (order_list.empty()) asks.erase(asks.begin());
            }
        } else {
            while (qty > 0 && !bids.empty()) {
                auto& order_list = bids.begin()->second;
                while (!order_list.empty() && qty > 0) {
                    auto match_order = order_list.front();
                    uint32_t fill = std::min(qty, match_order->qty);
                    qty -= fill;
                    match_order->qty -= fill;

                    send_fill(client_fd, client_req_id, order_id, fill, match_order->price, t_recv);
                    send_fill(match_order->client_fd, match_order->client_req_id, match_order->order_id, fill, match_order->price, t_recv);

                    if (match_order->qty == 0) {
                        active_orders.erase(match_order->order_id);
                        order_list.erase(order_list.begin());
                    }
                }
                if (order_list.empty()) bids.erase(bids.begin());
            }
        }
        if (qty > 0) {
            // Market orders remaining unfilled drop into void (no residual limit)
            send_reject(client_fd, client_req_id, order_id, 1); 
        }
    }

    void process_cancel_order(uint32_t client_req_id, int client_fd, uint32_t target_order_id) {
        auto it = active_orders.find(target_order_id);
        if (it != active_orders.end()) {
            auto order = it->second;
            if (order->is_buy) {
                auto& vec = bids[order->price];
                vec.erase(std::remove(vec.begin(), vec.end(), order), vec.end());
                if (vec.empty()) bids.erase(order->price);
            } else {
                auto& vec = asks[order->price];
                vec.erase(std::remove(vec.begin(), vec.end(), order), vec.end());
                if (vec.empty()) asks.erase(order->price);
            }
            active_orders.erase(it);
            // Confirm cancellation back via ACK packet channel structure
            send_ack(client_fd, client_req_id, target_order_id, 0);
        } else {
            send_reject(client_fd, client_req_id, target_order_id, 2); // Error code 2: Not found
        }
    }
};

// --- Client Session Socket Worker Handler ---
void handle_client(int client_fd, OrderBook& orderbook) {
    std::vector<uint8_t> buffer(1024);
    size_t data_buffered = 0;

    while (true) {
        ssize_t bytes_read = recv(client_fd, buffer.data() + data_buffered, buffer.size() - data_buffered, 0);
        if (bytes_read <= 0) {
            break; // Client disconnected
        }
        data_buffered += bytes_read;

        size_t cursor = 0;
        while (cursor < data_buffered) {
            uint8_t action_byte = buffer[cursor];
            Action act = static_cast<Action>(action_byte);
            size_t expected_len = 0;

            if (act == Action::BUY || act == Action::SELL || act == Action::MARKET_BUY || act == Action::MARKET_SELL) {
                expected_len = 13; // 1 + 4 (client_req_id) + 4 (size) + 4 (price) -> '!Biif'
            } else if (act == Action::CANCEL) {
                expected_len = 9;  // 1 + 4 (client_req_id) + 4 (order_id) -> '!Bii'
            } else {
                // Invalid byte stream chunk corruption handling
                cursor++;
                continue;
            }

            if (data_buffered - cursor < expected_len) {
                break; // Wait for full payload to arrive on wire socket stream
            }

            int64_t t_recv = std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::high_resolution_clock::now().time_since_epoch()).count();

            // Extract values matching python struct formatting bytes safely
            uint32_t client_req_id;
            std::memcpy(&client_req_id, &buffer[cursor + 1], 4);
            client_req_id = ntohl(client_req_id);

            if (act == Action::BUY || act == Action::SELL) {
                uint32_t size;
                float price;
                std::memcpy(&size, &buffer[cursor + 5], 4);
                std::memcpy(&price, &buffer[cursor + 9], 4);
                size = ntohl(size);
                price = ntohf(price);

                orderbook.process_limit_order(client_req_id, client_fd, size, price, (act == Action::BUY), t_recv);
            } 
            else if (act == Action::MARKET_BUY || act == Action::MARKET_SELL) {
                uint32_t size;
                std::memcpy(&size, &buffer[cursor + 5], 4);
                size = ntohl(size);

                orderbook.process_market_order(client_req_id, client_fd, size, (act == Action::MARKET_BUY), t_recv);
            } 
            else if (act == Action::CANCEL) {
                uint32_t order_id;
                std::memcpy(&order_id, &buffer[cursor + 5], 4);
                order_id = ntohl(order_id);

                orderbook.process_cancel_order(client_req_id, client_fd, order_id);
            }

            cursor += expected_len;
        }

        if (cursor > 0) {
            std::memmove(buffer.data(), buffer.data() + cursor, data_buffered - cursor);
            data_buffered -= cursor;
        }
    }
    close(client_fd);
}

int main() {

    const char* nomad_ip = std::getenv("NOMAD_IP");
    const char* nomad_port = std::getenv("NOMAD_PORT");

    std::string server_ip = nomad_ip ? nomad_ip : "0.0.0.0";
    int server_port = nomad_port ? std::stoi(nomad_port) : 8080;

    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(server_port);

    if (inet_pton(AF_INET, server_ip.c_str(), &address.sin_addr) <= 0) {
        std::cerr << "[-] Invalid IP address format: " << server_ip << ":" << server_port << std::endl;
        return -1;
    }

    if (bind(server_fd, (struct sockaddr*)&address, sizeof(address)) < 0) {
        std::cerr << "[-] Binding failed on " << server_ip << ":" << server_port << std::endl;
        return -1;
    }

    listen(server_fd, 128);
    std::cout << "[*] C++ Orderbook Engine running on " << server_ip << ":" << server_port << "..." << std::endl;
    
    OrderBook orderbook;
    while (true) {
        int client_id = accept(server_fd, nullptr, nullptr);
        if (client_id >= 0) {
            std::thread(handle_client, client_id, std::ref(orderbook)).detach();
        }
    }
    
    close(server_fd);
    return 0;
}
