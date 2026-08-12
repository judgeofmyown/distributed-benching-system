const ws_url = "ws://localhost:8000/ws/telemetry"
const metric_container = document.getElementById("metric")

function connectWebSocketTelemetry(){
    const socket = new WebSocket(ws_url);

    socket.onopen = () => {
        console.log("Telemetry UDP connected successfully...")
    };

    socket.onmessage = (event) => {
        const metric_message = JSON.parse(event.data);
        console.log("metric message got!!")
        if (metric_message.type == "BOT_TELE_BATCH"){
            const metric_list = metric_message.metrics;

            requestAnimationFrame(() => {
                renderMetrics(metric_list);
            });
        }else{
            console.error("Invalid message type")
        }
    }

    socket.onerror = (err) => {
        console.error("ES:Error ", err);
        socket.close();
    };
}

function renderMetrics(metric_list) {
    metric_container.innerHTML = metric_list.map(
        (item) => `
        <p>${item.name}, ${item.value}, ${item.unit}</p>
        `
    ).join("");
}

connectWebSocketTelemetry();