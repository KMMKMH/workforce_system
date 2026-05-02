const video = document.getElementById('video');

navigator.mediaDevices.getUserMedia({ video: true })
    .then(stream => video.srcObject = stream);

let step = 1;
let done = false
let running = false;
let processing = false;
let baseImage = null;

function startRegistration() {
    running = true;
    document.querySelector("button").disabled = true;
    document.getElementById("status").innerText = "Look straight";
    setStatus("instruction")
    loopCapture()
}

function loopCapture() {
    if (done) {
        return
    }

    if (!running || processing) {
        setTimeout(loopCapture, 2000);
        return;
    }

    captureFrame();
    setTimeout(loopCapture, 1500);
}

function captureFrame() {
    if (processing) return;
    processing = true;
    
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    ctx.drawImage(video, 0, 0);

    const imageData = canvas.toDataURL('image/jpeg');

    if (step == 1) {
        baseImage = imageData
    }

    fetch('/face/register/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
            image: imageData,
            base_image: baseImage,
            step: step
        })
    })
    .then(res => res.json())
    .then(data => {
        processing = false;
        setStatus(data.status)
        document.getElementById("status").innerText = data.message;

        if (data.next_step) {
            step = data.next_step;
        }

        if (data.success) {
            done = true;
            running = false;
            setTimeout(() => {
                window.location.href = "/face/verify/";
            }, 1000)
        }
    });
}

function getCSRFToken() {
    return document.cookie.split('; ')
        .find(row => row.startsWith('csrftoken'))
        .split('=')[1];
}

function setStatus(status) {
    document.getElementById("status").className = `status ${status}`
}