#include <iostream>
#include <vector>
#include <map>
#include <unordered_map>
#include <memory>
#include <string>
#include <cstring>
#include <chrono>
#include <thread>
#include <mutex>
#include <algorithm>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>

std::mutex log_mutex; // protects shared terminal printing, std::cout / std::cerr

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

enum class MDMsgType : uint8_t {
    BOOK_SNAPSHOT = 1,
    TRADE = 2
};

// --- Order & Data Structures ---
struct Order {
    uint32_t order_id;
    uint32_t client_req_id;
    int client_id;
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

    std::mutex book_mutex; // guarding internal memory structures of order matching engine

    bool md_enabled = false;
    int md_udp_sock = -1;
    sockaddr_in md_ui_addr{};
    uint64_t md_seq_num = 1;
    uint32_t md_trade_id = 1;

    void send_packet(int client_id, const std::vector<uint8_t>& packet) {
        uint8_t len = packet.size();
        send(client_id, &len, 1, 0); // Write length prefix byte
        send(client_id, packet.data(), len, 0);
    }

    void write_md_header(std::vector<uint8_t>& packet, MDMsgType type, size_t offset = 0) {
        uint8_t t = static_cast<uint8_t>(type);
        uint64_t seq = htonll(md_seq_num++);
        uint64_t ts = htonll(std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::high_resolution_clock::now().time_since_epoch()).count());
        
            packet[offset] = t;
        std::memcpy(&packet[offset + 1], &seq, 8);
        std::memcpy(&packet[offset + 9], &ts, 8);            
    }

    void broadcast_trade_event(float exec_price, uint32_t fill_qty) {
        if (!md_enabled) return;
            // Header(17) + trade_id(4) + price(4) + qty(4) = 29 Bytes
        size_t packet_size = 17 + 12;
        std::vector<uint8_t> packet(packet_size);
                
        write_md_header(packet, MDMsgType::TRADE);
                
        size_t cursor = 17;
        uint32_t t_id = htonl(md_trade_id++);
        uint32_t f_qty = htonl(fill_qty);
                
        uint32_t price_bin;
        std::memcpy(&price_bin, &exec_price, 4);
        price_bin = htonl(price_bin);

        std::memcpy(&packet[cursor], &t_id, 4);      cursor += 4;
        std::memcpy(&packet[cursor], &price_bin, 4); cursor += 4;
        std::memcpy(&packet[cursor], &f_qty, 4);
                
        sendto(md_udp_sock, packet.data(), packet.size(), 0, (struct sockaddr*)&md_ui_addr, sizeof(md_ui_addr));    
    }

public:

    void enable_market_data(int sock, const sockaddr_in& addr) {
        md_udp_sock = sock;
        md_ui_addr = addr;
        md_enabled = true;
    }
    
    void broadcast_market_data(size_t depth=5) {
        if (!md_enabled) return;

        std::vector<std::pair<float, uint32_t>> top_bids; 
        std::vector<std::pair<float, uint32_t>> top_asks;

        // critical section
        {
            std::lock_guard<std::mutex> lock(book_mutex);
            
            // top bids
            for (const auto& [price, order_list] : bids) {
                if (top_bids.size() >= depth) break;
                uint32_t total_qty = 0;
                for (const auto& order : order_list) {
                    total_qty += order->qty;
                }
                top_bids.push_back({price, total_qty});
            }
            
            // top asks
            for (const auto& [price, order_list] : asks) {
                if (top_asks.size() >= depth) break;
                uint32_t total_qty = 0;
                for (const auto& order : order_list) {
                    total_qty += order->qty;
                }
                top_asks.push_back({price, total_qty});
            }
        }
        
        uint8_t num_bids = static_cast<uint8_t>(top_bids.size());
        uint8_t num_asks = static_cast<uint8_t>(top_asks.size());
        
        size_t packet_size = 17 + 2 + (num_bids * 8) + (num_asks * 8);
        std::vector<uint8_t> packet(packet_size);

        write_md_header(packet, MDMsgType::BOOK_SNAPSHOT);
        
        size_t cursor = 17;
        packet[cursor++] = num_bids;
        packet[cursor++] = num_asks;

        for (const auto& [price, qty] : top_bids) {
            uint32_t price_bin;
            std::memcpy(&price_bin, &price, 4);
            price_bin = htonl(price_bin);
            uint32_t qty_bin = htonl(qty);
            std::memcpy(&packet[cursor], &price_bin, 4);  cursor += 4;
            std::memcpy(&packet[cursor], &qty_bin, 4);    cursor += 4;
        }

        for (const auto& [price, qty] : top_asks) {
            uint32_t price_bin;
            std::memcpy(&price_bin, &price, 4);
            price_bin = htonl(price_bin);
            uint32_t qty_bin = htonl(qty);

            std::memcpy(&packet[cursor], &price_bin, 4);  cursor += 4;
            std::memcpy(&packet[cursor], &qty_bin, 4);    cursor += 4;
        }

        sendto(md_udp_sock, packet.data(), packet.size(), 0, (struct sockaddr*)&md_ui_addr, sizeof(md_ui_addr));
    }

    void send_ack(int client_id, uint32_t client_req_id, uint32_t order_id, int64_t t_recv) {
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

        send_packet(client_id, buffer);
    }

    void send_fill(int client_id, uint32_t client_req_id, uint32_t order_id, uint32_t fill_qty, float exec_price, int64_t t_recv) {
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

        send_packet(client_id, buffer);
    }

    void send_reject(int client_id, uint32_t client_req_id, uint32_t order_id, uint8_t error_code) {
        // Bot expectation mismatch workaround: Bot reads length 10 as '!BiiB' (1 + 4 + 4 + 1)
        std::vector<uint8_t> buffer(10);
        uint8_t msg_type = static_cast<uint8_t>(ServerMsg::REJECT);
        uint32_t r_id = htonl(client_req_id);
        uint32_t o_id = htonl(order_id);

        std::memcpy(&buffer[0], &msg_type, 1);
        std::memcpy(&buffer[1], &r_id, 4);
        std::memcpy(&buffer[5], &o_id, 4);
        std::memcpy(&buffer[9], &error_code, 1);

        send_packet(client_id, buffer);
    }

    void process_limit_order(uint32_t client_req_id, int client_id, uint32_t qty, float price, bool is_buy, int64_t t_recv) {
        
        std::lock_guard<std::mutex> lock(book_mutex);        

        uint32_t order_id = next_order_id++;
        
        // Instant ACK back to bot
        send_ack(client_id, client_req_id, order_id, t_recv);

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
                    send_fill(client_id, client_req_id, order_id, fill, match_order->price, t_recv);
                    send_fill(match_order->client_id, match_order->client_req_id, match_order->order_id, fill, match_order->price, t_recv);
                    
                    broadcast_trade_event(match_order->price, fill);

                    if (match_order->qty == 0) {
                        active_orders.erase(match_order->order_id);
                        order_list.erase(order_list.begin());
                    }
                }
                if (order_list.empty()) asks.erase(asks.begin());
            }

            if (qty > 0) {
                auto new_order = std::make_shared<Order>(Order{order_id, client_req_id, client_id, qty, price, true});
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

                    send_fill(client_id, client_req_id, order_id, fill, match_order->price, t_recv);
                    send_fill(match_order->client_id, match_order->client_req_id, match_order->order_id, fill, match_order->price, t_recv);
                    
                    broadcast_trade_event(match_order->price, fill);

                    if (match_order->qty == 0) {
                        active_orders.erase(match_order->order_id);
                        order_list.erase(order_list.begin());
                    }
                }
                if (order_list.empty()) bids.erase(bids.begin());
            }

            if (qty > 0) {
                auto new_order = std::make_shared<Order>(Order{order_id, client_req_id, client_id, qty, price, false});
                asks[price].push_back(new_order);
                active_orders[order_id] = new_order;
            }
        }
    }

    void process_market_order(uint32_t client_req_id, int client_id, uint32_t qty, bool is_buy, int64_t t_recv) {
        std::lock_guard<std::mutex> lock(book_mutex);

        uint32_t order_id = next_order_id++;
        send_ack(client_id, client_req_id, order_id, t_recv);

        if (is_buy) {
            while (qty > 0 && !asks.empty()) {
                auto& order_list = asks.begin()->second;
                while (!order_list.empty() && qty > 0) {
                    auto match_order = order_list.front();
                    uint32_t fill = std::min(qty, match_order->qty);
                    qty -= fill;
                    match_order->qty -= fill;

                    send_fill(client_id, client_req_id, order_id, fill, match_order->price, t_recv);
                    send_fill(match_order->client_id, match_order->client_req_id, match_order->order_id, fill, match_order->price, t_recv);

                    broadcast_trade_event(match_order->price, fill);

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

                    send_fill(client_id, client_req_id, order_id, fill, match_order->price, t_recv);
                    send_fill(match_order->client_id, match_order->client_req_id, match_order->order_id, fill, match_order->price, t_recv);
                    
                    broadcast_trade_event(match_order->price, fill);

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
            send_reject(client_id, client_req_id, order_id, 1); 
        }
    }

    void process_cancel_order(uint32_t client_req_id, int client_id, uint32_t target_order_id) {
        std::lock_guard<std::mutex> lock(book_mutex);

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
            send_ack(client_id, client_req_id, target_order_id, 0);
        } else {
            send_reject(client_id, client_req_id, target_order_id, 2); // Error code 2: Not found
        }
    }
};

// --- Client Session Socket Worker Handler ---
void handle_client(int client_id, OrderBook& orderbook) {
    std::vector<uint8_t> buffer(1024);
    size_t data_buffered = 0;

    while (true) {
        if (data_buffered >= buffer.size()) {
            std::lock_guard<std::mutex> lock(log_mutex);
            std::cerr << "[-] Dynamic framing failure, closing ID: " << client_id << std::endl;
            break;
        }

        ssize_t bytes_read = recv(client_id, buffer.data() + data_buffered, buffer.size() - data_buffered, 0);
        if (bytes_read <= 0) {
            break; // Client disconnected
        }
        std::cerr << "[DEBUG] recv() returned: "
          << bytes_read
          << " bytes, client FD: "
          << client_id
          << std::endl;

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
                orderbook.process_limit_order(client_req_id, client_id, size, price, (act == Action::BUY), t_recv);
                // orderbook.print_orderbook();
            } 
            else if (act == Action::MARKET_BUY || act == Action::MARKET_SELL) {
                uint32_t size;
                std::memcpy(&size, &buffer[cursor + 5], 4);
                size = ntohl(size);

                orderbook.process_market_order(client_req_id, client_id, size, (act == Action::MARKET_BUY), t_recv);
                // orderbook.print_orderbook();  
            } 
            else if (act == Action::CANCEL) {
                uint32_t order_id;
                std::memcpy(&order_id, &buffer[cursor + 5], 4);
                order_id = ntohl(order_id);

                orderbook.process_cancel_order(client_req_id, client_id, order_id);
                // orderbook.print_orderbook();
            }

            cursor += expected_len;
        }

        if (cursor > 0) {
            std::memmove(buffer.data(), buffer.data() + cursor, data_buffered - cursor);
            data_buffered -= cursor;
        }
    }
    struct sockaddr_in peer_addr;
    socklen_t peer_len = sizeof(peer_addr);
    if (getpeername(client_id, (struct sockaddr*)&peer_addr, &peer_len) == 0) {
        std::cout << "[-] Client disconnected: " << inet_ntoa(peer_addr.sin_addr) 
                  << ":" << ntohs(peer_addr.sin_port) << " (FD: " << client_id << ")" << std::endl;
    } else {
        std::cout << "[-] Client disconnected (FD: " << client_id << ")" << std::endl;
    }
    close(client_id);
}

int main() {

    const char* nomad_ip = std::getenv("NOMAD_IP");
    const char* nomad_port = std::getenv("NOMAD_PORT");

    std::string server_ip = nomad_ip ? nomad_ip : "0.0.0.0";
    int server_port = nomad_port ? std::stoi(nomad_port) : 8080;

    int server_id = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(server_id, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(server_port);

    if (inet_pton(AF_INET, server_ip.c_str(), &address.sin_addr) <= 0) {
        std::cerr << "[-] Invalid IP address format: " << server_ip << ":" << server_port << std::endl;
        return -1;
    }

    if (bind(server_id, (struct sockaddr*)&address, sizeof(address)) < 0) {
        std::cerr << "[-] Binding failed on " << server_ip << ":" << server_port << std::endl;
        return -1;
    }

    listen(server_id, 128);
    std::cout << "[*] C++ Orderbook Engine running on " << server_ip << ":" << server_port << "..." << std::endl;
    
    OrderBook orderbook;
    
    const char* env_ui_ip = std::getenv("MD_UI_IP");
    const char* env_ui_port = std::getenv("MD_UI_PORT");
    std::string ui_ip = env_ui_ip ? env_ui_ip : "127.0.0.1";
    int ui_port = env_ui_port ? std::stoi(env_ui_port) : 9999;

    int udp_sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (udp_sock >= 0) {
        sockaddr_in ui_addr{};
        ui_addr.sin_family = AF_INET;
        ui_addr.sin_port = htons(ui_port);
        inet_pton(AF_INET, ui_ip.c_str(), &ui_addr.sin_addr);
        
        orderbook.enable_market_data(udp_sock, ui_addr);
        
        std::cout << "[*] UDP Market Data feed active to " << ui_ip << ":" << ui_port << "..." << std::endl;

        // Dedicated snapshot publisher thread
        std::thread([&orderbook]() {
            while (true) {
                std::this_thread::sleep_for(std::chrono::milliseconds(50));
                orderbook.broadcast_market_data(5);
            }
        }).detach();
    }

    while (true) {
        sockaddr_in client_addr{};
        socklen_t client_len = sizeof(client_addr);

        int client_id = accept(server_id, (struct sockaddr*)&client_addr, &client_len);
        if (client_id >= 0) {
            char ip_str[INET_ADDRSTRLEN] = {0};
            inet_ntop(AF_INET, &(client_addr.sin_addr), ip_str, INET_ADDRSTRLEN);

            {
                std::lock_guard<std::mutex> lock(log_mutex);
                std::cout << "[+] Client connected from " << ip_str 
                          << ":" << ntohs(client_addr.sin_port) << " (ID: " << client_id << ")" << std::endl;
            }
            std::thread(handle_client, client_id, std::ref(orderbook)).detach();
        }
    }
    
    close(server_id);
    return 0;
}