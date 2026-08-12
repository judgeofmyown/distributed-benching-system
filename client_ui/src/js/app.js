const uploadForm = document.getElementById("uploadCode");
const ws = new WebSocket('ws://localhost:3000');

const asksSection = document.getElementById('asks-section');
const bidsSection = document.getElementById('bids-section');
const spreadSection = document.getElementById('spread-section');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    // Clear prior frames
    asksSection.innerHTML = '';
    bidsSection.innerHTML = '';

    // Render Asks (highest down to best ask)
    const reversedAsks = [...data.asks].reverse();
    reversedAsks.forEach(ask => {
        asksSection.innerHTML += `
            <div class="row ask">
                <span>${ask.price.toFixed(2)}</span>
                <span>${ask.qty}</span>
            </div>`;
    });

    // Calculate Spread
    const bestBid = data.bids.length > 0 ? data.bids[0].price : 0;
    const bestAsk = data.asks.length > 0 ? data.asks[0].price : 0;
    spreadSection.innerText = `SPREAD: ${Math.abs(bestAsk - bestBid).toFixed(2)}`;

    // Render Bids (best bid down to lowest)
    data.bids.forEach(bid => {
        bidsSection.innerHTML += `
            <div class="row bid">
                <span>${bid.price.toFixed(2)}</span>
                <span>${bid.qty}</span>
            </div>`;
    });
};
ws.onopen = () => console.log("[+] Connected to Node.js Server Layer");
ws.onclose = () => console.log("[-] Disconnected from Server Layer");

uploadForm.addEventListener('submit', async (event) => {
    event.preventDefault(); // stops page from reloading

    const fileInput = document.getElementById('file')

    if (fileInput.files.length == 0) {
        alert('Please select a file first.');        
        return;
    }

    const file = fileInput.files[0];

    const formData = new FormData();
    formData.append('uploadFile', file);

    try {
        const reponse = await fetch('', {
            method = 'POST',
            body = formData
        });

        if (response.ok) {
            alert('File uploaded successfully');
            
        } else {
            alert('Upload failed');
        }
    } catch(error) {
        console.error('error occured during upload', error);
    }
});


