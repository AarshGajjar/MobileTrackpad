import asyncio
import pyautogui
import socket
import json
import sys
from aiohttp import web
import logging
from ctypes import windll

# Disable unnecessary logging
logging.getLogger('websockets').setLevel(logging.ERROR)
logging.getLogger('aiohttp.access').setLevel(logging.ERROR)

# Configure pyautogui
pyautogui.FAILSAFE = False
pyautogui.MINIMUM_DURATION = 0
pyautogui.MINIMUM_SLEEP = 0
pyautogui.PAUSE = 0

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

MOBILE_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Trackpad</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        :root {
            --primary-bg: #1a1a1a;
            --secondary-bg:rgb(151, 234, 255);
            --accent-color: #4a90e2;
            --text-color: #ffffff;
        }
        body {
            margin: 0;
            padding: 0;
            overflow: hidden;
            background: var(--primary-bg);
            touch-action: none;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            user-select: none;
            -webkit-user-select: none;
            position: fixed;
            width: 100%;
            height: 100%;
            color: var(--text-color);
        }
        #container {
            position: fixed;
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
        }
        #header {
            padding: 10px;
            background: linear-gradient(145deg,rgb(40, 36, 42) 0%,rgb(47, 49, 46) 100%);
            display: flex;
            justify-content: space-between;
            align-items: center;
            z-index: 1000;
        }
        #fullscreen-btn {
            background: var(--accent-color);
            border: none;
            color: white;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
        }
        #main-area {
            flex: 1;
            display: flex;
            position: relative;
        }
        #trackpad {
            flex: 1;
            background: linear-gradient(145deg, #1f1f1f 0%, #2d2d2d 100%);
            touch-action: none;
            position: relative;
        }
        #scrollbar {
            width: 20px;
            background: rgb(255, 255, 255);
            touch-action: none;
            position: relative;
        }
        #zoombar {
            height: 60px;
            background: var(--secondary-bg);
            touch-action: none;
            position: relative;
        }
        .bar-indicator {
            position: absolute;
            background: rgb(255, 0, 0);
            border-radius: 4px;
            transition: opacity 0.2s;
        }
        #scroll-indicator {
            width: 20px;
            height: 100px;
            right: 0;
            opacity: 0;
        }
        #zoom-indicator {
            width: 100px;
            height: 60px;
            bottom: 0;
            opacity: 0;
        }
        .touch-feedback {
            position: absolute;
            width: 20px;
            height: 20px;
            background: rgba(74, 144, 226, 0.3);
            border-radius: 50%;
            pointer-events: none;
            transform: translate(-50%, -50%);
            transition: opacity 0.3s;
        }
    </style>
</head>
<body>
    <div id="container">
        <div id="header">
            <span>Mobile Trackpad</span>
            <button id="fullscreen-btn">Fullscreen</button>
        </div>
        <div id="main-area">
            <div id="trackpad"></div>
            <div id="scrollbar">
                <div id="scroll-indicator" class="bar-indicator"></div>
            </div>
        </div>
        <div id="zoombar">
            <div id="zoom-indicator" class="bar-indicator"></div>
        </div>
    </div>

    <script>
        let ws;
        let lastTouches = {};
        let touchStartTime = 0;
        let initialTouchPos = null;
        let isTapping = false;
        let threeFingerStartX = null;
        let lastEventTime = 0;
        let eventQueue = [];
        let animationFrameId = null;
        let zoomStartX = null;
        let lastZoomEvent = 0;
        let zoomThreshold = 100; // Minimum pixels to trigger zoom
        let twoFingerStartY = null;
        let lastTwoFingerY = null;
        
        const twoFingerScrollSensitivity = 0.1;
        const mouseSensitivity = 3.5;
        const scrollSensitivity = 1.0;
        
        // Gesture settings
        const TAP_THRESHOLD = 150;
        const MOVE_THRESHOLD = 3;
        const THREE_FINGER_SWIPE_THRESHOLD = 50;
        const ZOOM_COOLDOWN = 300; // Minimum ms between zoom events

        // Fullscreen handling
        const fullscreenBtn = document.getElementById('fullscreen-btn');
        fullscreenBtn.addEventListener('click', () => {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen();
                fullscreenBtn.textContent = 'Exit Fullscreen';
            } else {
                document.exitFullscreen();
                fullscreenBtn.textContent = 'Fullscreen';
            }
        });

        document.addEventListener('fullscreenchange', () => {
            fullscreenBtn.textContent = document.fullscreenElement ? 'Exit Fullscreen' : 'Fullscreen';
        });

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
            ws.onclose = () => setTimeout(connectWebSocket, 1000);
            if (ws.bufferedAmount === undefined) {
                ws.bufferedAmount = 0;
            }
        }

        connectWebSocket();

        function processEventQueue() {
            const now = performance.now();
            if (eventQueue.length > 0 && now - lastEventTime >= 16) {
                const event = eventQueue.pop();
                eventQueue = [];
                if (ws?.readyState === WebSocket.OPEN && ws.bufferedAmount === 0) {
                    ws.send(JSON.stringify(event));
                    lastEventTime = now;
                }
            }
            animationFrameId = requestAnimationFrame(processEventQueue);
        }

        function queueEvent(event) {
            eventQueue.push(event);
            if (!animationFrameId) {
                animationFrameId = requestAnimationFrame(processEventQueue);
            }
        }

        function createTouchFeedback(x, y) {
            const feedback = document.createElement('div');
            feedback.className = 'touch-feedback';
            feedback.style.left = x + 'px';
            feedback.style.top = y + 'px';
            document.body.appendChild(feedback);
            setTimeout(() => feedback.remove(), 300);
        }

        function handleTrackpadTouch(e) {
            const touches = Array.from(e.touches);
            const numTouches = touches.length;

            if (numTouches === 1) {
                const touch = touches[0];
                const touchId = touch.identifier;
                const prevTouch = lastTouches[touchId];
                
                if (prevTouch) {
                    const deltaX = (touch.clientX - prevTouch.clientX) * mouseSensitivity;
                    const deltaY = (touch.clientY - prevTouch.clientY) * mouseSensitivity;
                    
                    if (Math.abs(deltaX) > 0 || Math.abs(deltaY) > 0) {
                        isTapping = false;
                        queueEvent({type: 'move', x: deltaX, y: deltaY});
                    }
                }
                lastTouches[touchId] = { clientX: touch.clientX, clientY: touch.clientY };
                createTouchFeedback(touch.clientX, touch.clientY);
            }
            else if (numTouches === 2) {
                // Handle two-finger scrolling
                const touch1 = touches[0];
                const touch2 = touches[1];
                const currentY = (touch1.clientY + touch2.clientY) / 2;
                
                if (lastTwoFingerY !== null) {
                    const deltaY = (currentY - lastTwoFingerY) * twoFingerScrollSensitivity;
                    queueEvent({type: 'scroll', x: 0, y: deltaY});
                }
                
                lastTwoFingerY = currentY;
                
                // Create touch feedback for both fingers
                createTouchFeedback(touch1.clientX, touch1.clientY);
                createTouchFeedback(touch2.clientX, touch2.clientY);
            }
            else if (numTouches === 3) {
                if (!threeFingerStartX) {
                    threeFingerStartX = (touches[0].clientX + touches[1].clientX + touches[2].clientX) / 3;
                } else {
                    const currentX = (touches[0].clientX + touches[1].clientX + touches[2].clientX) / 3;
                    const swipeDistance = currentX - threeFingerStartX;

                    if (Math.abs(swipeDistance) > THREE_FINGER_SWIPE_THRESHOLD) {
                        queueEvent({type: 'nextWindow'});
                        threeFingerStartX = currentX;
                    }
                }
            }
        }

        function handleScrollbarTouch(e) {
            const touch = e.touches[0];
            const touchId = touch.identifier;
            const prevTouch = lastTouches[touchId];
            
            if (prevTouch) {
                const deltaY = (touch.clientY - prevTouch.clientY) * scrollSensitivity;
                queueEvent({type: 'scroll', x: 0, y: deltaY});
            }
            lastTouches[touchId] = { clientX: touch.clientX, clientY: touch.clientY };
            
            const indicator = document.getElementById('scroll-indicator');
            indicator.style.top = `${touch.clientY - indicator.offsetHeight/2}px`;
            indicator.style.opacity = '1';
        }

        function handleZoombarTouch(e) {
            const touch = e.touches[0];
            const touchId = touch.identifier;
            
            if (!zoomStartX) {
                zoomStartX = touch.clientX;
                return;
            }
            
            const now = Date.now();
            const deltaX = touch.clientX - zoomStartX;
            
            if (Math.abs(deltaX) >= zoomThreshold && now - lastZoomEvent >= ZOOM_COOLDOWN) {
                queueEvent({
                    type: 'zoom',
                    scale: deltaX > 0 ? 1.1 : 0.9
                });
                zoomStartX = touch.clientX;
                lastZoomEvent = now;
            }
            
            const indicator = document.getElementById('zoom-indicator');
            indicator.style.left = `${touch.clientX - indicator.offsetWidth/2}px`;
            indicator.style.opacity = '1';
        }

        const trackpad = document.getElementById('trackpad');
        const scrollbar = document.getElementById('scrollbar');
        const zoombar = document.getElementById('zoombar');

        // Trackpad events
        trackpad.addEventListener('touchstart', (e) => {
    e.preventDefault();
    touchStartTime = Date.now();
    isTapping = true;
    initialTouchPos = {
        x: e.touches[0].clientX,
        y: e.touches[0].clientY
    };
});

        trackpad.addEventListener('touchmove', (e) => {
            e.preventDefault();
            handleTrackpadTouch(e);
        });

        trackpad.addEventListener('touchend', (e) => {
            e.preventDefault();
            if (e.touches.length === 0) {
                if (isTapping && (Date.now() - touchStartTime) < TAP_THRESHOLD) {
                    queueEvent({type: 'click', button: 'left'});
                }
                threeFingerStartX = null;
                lastTouches = {};
            }
            initialTouchPos = null;
        });

        // Scrollbar events
        scrollbar.addEventListener('touchstart', (e) => {
            e.preventDefault();
            handleScrollbarTouch(e);
        });

        scrollbar.addEventListener('touchmove', (e) => {
            e.preventDefault();
            handleScrollbarTouch(e);
        });

        scrollbar.addEventListener('touchend', (e) => {
            e.preventDefault();
            lastTouches = {};
            document.getElementById('scroll-indicator').style.opacity = '0';
        });

        // Zoombar events
        zoombar.addEventListener('touchstart', (e) => {
            e.preventDefault();
            zoomStartX = e.touches[0].clientX;
            handleZoombarTouch(e);
        });

        zoombar.addEventListener('touchmove', (e) => {
            e.preventDefault();
            handleZoombarTouch(e);
        });

        zoombar.addEventListener('touchend', (e) => {
            e.preventDefault();
            lastTouches = {};
            zoomStartX = null;
            document.getElementById('zoom-indicator').style.opacity = '0';
        });

        // Cleanup
        window.addEventListener('beforeunload', () => {
            if (animationFrameId) {
                cancelAnimationFrame(animationFrameId);
            }
        });
    </script>
</body>
</html>
'''

async def websocket_handler(request):
    ws = web.WebSocketResponse(timeout=1)
    await ws.prepare(request)

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            data = json.loads(msg.data)
            
            if data['type'] == 'move':
                pyautogui.moveRel(data['x'], data['y'], duration=0)
            
            elif data['type'] == 'click':
                pyautogui.click(button=data['button'])
            
            elif data['type'] == 'scroll':
                scroll_amount = int(data['y'] * -60)
                windll.user32.mouse_event(0x0800, 0, 0, scroll_amount, 0)
            
            elif data['type'] == 'zoom':
                if data['scale'] > 1:
                    pyautogui.hotkey('ctrl', '+')
                else:
                    pyautogui.hotkey('ctrl', '-')
            
            elif data['type'] == 'nextWindow':
                pyautogui.hotkey('alt', 'tab')

    return ws

async def index_handler(request):
    return web.Response(text=MOBILE_HTML, content_type='text/html')

async def main():
    app = web.Application()
    app.router.add_get('/', index_handler)
    app.router.add_get('/ws', websocket_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 5000)
    
    ip_address = get_local_ip()
    print(f"\nMobile Trackpad Server")

    print(f"====================")
    print(f"Connect to: http://{ip_address}:5000")
    print(f"Press Ctrl+C to stop the server\n")
    
    await site.start()
    await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped")
        sys.exit(0)