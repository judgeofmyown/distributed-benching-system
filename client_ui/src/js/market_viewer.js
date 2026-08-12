const ws_url = "ws://localhost:8000/ws/market";
// ws.onopen = () => console.log("websocket connected successfully!!!")
// ws.onerror = (err) => console.error("❌ WebSocket Error:", err);
const bidsContainer = document.getElementById("bids-list");
const asksContainer = document.getElementById("asks-list");
const statusEl = document.getElementById("status");

function connectWebSocket() {
    const socket = new WebSocket(ws_url);

    socket.onopen = () => {
        console.log("websocket connected successfully!!!")
        statusEl.textContent = "* Live Stream Connected";
        statusEl.className = "connection-status status-online";
    };

    socket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        console.log("message got!!")
        if (message.type == "MARKET_DATA_BATCH") {
            if (Array.isArray(message.updates) && message.updates.length>0) {
                const latestTick = message.updates[message.updates.length - 1];

                requestAnimationFrame(() => {
                    renderOrderBook(latestTick.bids, latestTick.asks);
                });
            }
        } else if (message.snapshot?.bids && message.snapshot?.asks) {
            requestAnimationFrame(() => {
                renderOrderBook(message.snapshot.bids, message.snapshot.asks);
            });
        }
    };

    socket.onclose = () => {
        statusEl.textContent = "○ Disconnected. Reconnecting in 2s...";
        statusEl.className = "connection-status status-offline";
        setTimeout(connectWebSocket, 2000);
    };

    socket.onerror = (err) => {
        console.error("WS Error:", err);
        socket.close();
    };
}

function renderOrderBook(bids = [], asks = []) {
    const sortedBids = [...bids].sort((a, b) => b.price - a.price);
    const sortedAsks = [...asks].sort((a, b) => a.price - b.price);

    bidsContainer.innerHTML = sortedBids
        .map(
        (item) => `
        <div class="order-row">
            <span class="price">${item.price.toFixed(2)}</span>
            <span class="qty">${item.qty}</span>
        </div>`
        )
        .join("");
    asksContainer.innerHTML = sortedAsks
        .map(
          (item) => `
          <div class="order-row">
            <span class="price">${item.price.toFixed(2)}</span>
            <span class="qty">${item.qty}</span>
          </div>`
        )
        .join("");
}
connectWebSocket();