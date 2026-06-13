const uploadForm = document.getElementById("uploadCode");

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
