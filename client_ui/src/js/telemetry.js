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
            const metric_dict = metric_message.metrics;

            requestAnimationFrame(() => {
                renderMetrics(metric_dict);
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

function renderMetrics(metric_dict) {
    metric_container.innerHTML = Object.entries(metric_dict).map(
        ([name, value]) => `
            <p>${name} -> ${value}</p>
        `
    )
}

connectWebSocketTelemetry();