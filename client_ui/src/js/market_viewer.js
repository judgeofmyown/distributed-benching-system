const ws_url = "ws://localhost:8000/ws/market";

const bidsContainer = document.getElementById("bids-list");
const asksContainer = document.getElementById("asks-list");
const statusEl = document.getElementById("status");
const priceChartContainer = document.getElementById("price-chart");
const spreadChartContainer = document.getElementById("spread-chart");
const commonChartOptions = {

    layout: {
        background: {
            color: "#131722"
        },
        textColor: "#d1d4dc"
    },

    grid: {
        vertLines: {
            color: "#2B2B43"
        },
        horzLines: {
            color: "#2B2B43"
        }
    },

    timeScale: {
        borderColor: "#3a3f4b",
        timeVisible: true,
        secondsVisible: true,
        // Default zoom
        barSpacing: 6,
        minBarSpacing: 2,

        // Keep some space to the right of the latest candle/point
        rightOffset: 5
    },

    rightPriceScale: {
        borderColor: "#3a3f4b"
    },

    crosshair: {
        mode: 0
    }
};


/* =========================================================
   PRICE CHART
   ========================================================= */

const priceChart = LightweightCharts.createChart(
    priceChartContainer,
    {
        ...commonChartOptions,

        width: priceChartContainer.clientWidth,
        height: priceChartContainer.clientHeight
    }
);


/* Volume */

const volumeSeries = priceChart.addHistogramSeries({
    color: "#26a69a",

    priceFormat: {
        type: "volume"
    },

    priceScaleId: ""
});

priceChart.priceScale("").applyOptions({
    scaleMargins: {
        top: 0.80,
        bottom: 0
    }
});


/* Price series */

const askSeries = priceChart.addLineSeries({
    color: "#ef5350",
    lineWidth: 1,
    title: "Best Ask"
});

const midSeries = priceChart.addLineSeries({
    color: "#E1E1E1",
    lineWidth: 2,
    title: "Mid Price"
});

const bidSeries = priceChart.addLineSeries({
    color: "#26a69a",
    lineWidth: 1,
    title: "Best Bid"
});


/* =========================================================
   SPREAD CHART
   ========================================================= */

const spreadChart = LightweightCharts.createChart(
    spreadChartContainer,
    {
        ...commonChartOptions,

        width: spreadChartContainer.clientWidth,
        height: spreadChartContainer.clientHeight
    }
);


const spreadSeries = spreadChart.addLineSeries({
    color: "#FF9800",
    lineWidth: 2,
    title: "Spread"
});


/* =========================================================
   CHART SYNCHRONIZATION
   ========================================================= */

priceChart.timeScale().subscribeVisibleTimeRangeChange(range => {

    if (range) {
        spreadChart.timeScale().setVisibleRange(range);
    }

});

spreadChart.timeScale().subscribeVisibleTimeRangeChange(range => {

    if (range) {
        priceChart.timeScale().setVisibleRange(range);
    }

});

function resizeCharts() {

    priceChart.resize(
        priceChartContainer.clientWidth,
        priceChartContainer.clientHeight
    );

    spreadChart.resize(
        spreadChartContainer.clientWidth,
        spreadChartContainer.clientHeight
    );
}


const resizeObserver = new ResizeObserver(() => {
    resizeCharts();
});

resizeObserver.observe(priceChartContainer);
resizeObserver.observe(spreadChartContainer);

const CHART_INTERVAL_SEC = 1;

let currentInterval = null;
let currentVolume = 0;

function updateCharts(
    timestamp_ns,
    bids,
    asks,
    trade_qty = 0
) {

    if (!timestamp_ns) {
        return;
    }


    /*
     * Convert nanoseconds → seconds.
     *
     * Lightweight Charts uses Unix seconds.
     */

    const timeInSeconds =
        Math.floor(timestamp_ns / 1_000_000_000);


    /*
     * Aggregate into 1-second buckets.
     */

    const intervalTime =
        Math.floor(timeInSeconds / CHART_INTERVAL_SEC)
        * CHART_INTERVAL_SEC;


    /*
     * Ignore out-of-order market data.
     */

    if (
        currentInterval !== null &&
        intervalTime < currentInterval
    ) {
        return;
    }


    /* =====================================================
       VOLUME
       ===================================================== */

    if (intervalTime !== currentInterval) {

        currentInterval = intervalTime;

        currentVolume = trade_qty;

    } else {

        currentVolume += trade_qty;

    }


    if (trade_qty > 0) {

        volumeSeries.update({
            time: currentInterval,
            value: currentVolume,
            color: "#4c525e"
        });

    }

    if (
        bids &&
        asks &&
        bids.length > 0 &&
        asks.length > 0
    ) {

        const bestBid = Math.max(
            ...bids.map(b => b.price)
        );

        const bestAsk = Math.min(
            ...asks.map(a => a.price)
        );


        const midPrice =
            (bestBid + bestAsk) / 2;

        const spread =
            bestAsk - bestBid;


        /* Update price chart */

        bidSeries.update({
            time: currentInterval,
            value: bestBid
        });

        askSeries.update({
            time: currentInterval,
            value: bestAsk
        });

        midSeries.update({
            time: currentInterval,
            value: midPrice
        });


        /* Update spread chart */

        spreadSeries.update({
            time: currentInterval,
            value: spread
        });

        priceChart.timeScale().scrollToRealTime();
        spreadChart.timeScale().scrollToRealTime();

    }

}

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
            if (Array.isArray(message.updates) && message.updates.length > 0) {
                message.updates.forEach(update => {
                    if (update.type === "BOOK_SNAPSHOT") {
                        updateCharts(update.timestamp, update.bids, update.asks, 0);
                    } else if (update.type === "TRADE") {
                        updateCharts(update.timestamp, null, null, update.qty);
                    }
                });
            }

            // 2. Render Order Book (Now Uncommented!)
            if (message.snapshot && message.snapshot.bids && message.snapshot.asks) {
                requestAnimationFrame(() => {
                    renderOrderBook(message.snapshot.bids, message.snapshot.asks);
                });
            }
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