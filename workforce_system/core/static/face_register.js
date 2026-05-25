const video = document.getElementById('video');
const startButton = document.querySelector("button");
const startButtonText = startButton ? startButton.innerText : "";

let step = 1;
let done = false
let running = false;
let processing = false;
let baseImage = null;
let cameraStream = null;
let started = false;

function cameraErrorMessage(error) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        return "Camera access is not supported in this browser.";
    }

    if (error && (error.name === "NotAllowedError" || error.name === "PermissionDeniedError")) {
        return "Camera permission is required. Please allow camera access, then press Start Registration again.";
    }

    if (error && (error.name === "NotFoundError" || error.name === "DevicesNotFoundError")) {
        return "No camera was found on this device.";
    }

    return "Could not start the camera. Please check camera access and try again.";
}

function resetStartButton() {
    if (startButton) {
        startButton.disabled = false;
        startButton.innerText = startButtonText;
    }
}

async function ensureCameraReady() {
    if (cameraStream && video.srcObject) {
        return true;
    }

    try {
        cameraStream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = cameraStream;
        await new Promise(resolve => {
            if (video.readyState >= 2) {
                resolve();
                return;
            }

            video.onloadedmetadata = resolve;
        });
        return true;
    } catch (error) {
        started = false;
        running = false;
        processing = false;
        setStatus("error");
        document.getElementById("status").innerText = cameraErrorMessage(error);
        resetStartButton();
        return false;
    }
}

async function startRegistration() {
    if (started || running || done) return;

    started = true;
    if (startButton) {
        startButton.disabled = true;
        startButton.innerText = "Registering...";
    }

    const cameraReady = await ensureCameraReady();
    if (!cameraReady) return;

    running = true;
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
    if (!video.videoWidth || !video.videoHeight) {
        setStatus("warning");
        document.getElementById("status").innerText = "Camera is still starting. Please wait a moment.";
        return;
    }

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
    })
    .catch(() => {
        started = false;
        processing = false;
        running = false;
        setStatus("error");
        document.getElementById("status").innerText = "Registration failed. Please try again.";
        resetStartButton();
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
