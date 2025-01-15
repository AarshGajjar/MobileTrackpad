import asyncio
import pyautogui
import socket
import json
import sys
from aiohttp import web
import logging
from ctypes import windll
from collections import deque
import time

# Disable unnecessary logging
logging.getLogger('websockets').setLevel(logging.ERROR)
logging.getLogger('aiohttp.access').setLevel(logging.ERROR)

# Configure pyautogui
pyautogui.FAILSAFE = False
pyautogui.MINIMUM_DURATION = 0
pyautogui.MINIMUM_SLEEP = 0
pyautogui.PAUSE = 0

# Movement smoothing settings
MOVEMENT_BUFFER_SIZE = 3  # Number of movements to average
MOVEMENT_THRESHOLD = 0.1  # Minimum movement to register
MAX_QUEUE_SIZE = 10  # Maximum number of events to queue

MOUSE_SENSITIVITY = 3.5
SCROLL_SENSITIVITY = 10

def update_sensitivities(mouse_sens, scroll_sens):
    """Update the sensitivity values and regenerate the HTML with new values"""
    global MOUSE_SENSITIVITY, SCROLL_SENSITIVITY
    MOUSE_SENSITIVITY = mouse_sens
    SCROLL_SENSITIVITY = scroll_sens
    return MOBILE_HTML.replace(
        '${MOUSE_SENSITIVITY}', str(MOUSE_SENSITIVITY)
    ).replace(
        '${SCROLL_SENSITIVITY}', str(SCROLL_SENSITIVITY)
    )

class MovementBuffer:
    def __init__(self, size=MOVEMENT_BUFFER_SIZE):
        self.buffer_x = deque(maxlen=size)
        self.buffer_y = deque(maxlen=size)
        self.last_process_time = time.time()
        self.accumulated_x = 0
        self.accumulated_y = 0

    def add_movement(self, x, y):
        self.buffer_x.append(x)
        self.buffer_y.append(y)
        self.accumulated_x += x
        self.accumulated_y += y

    def get_smooth_movement(self):
        if not self.buffer_x or not self.buffer_y:
            return 0, 0

        current_time = time.time()
        time_delta = current_time - self.last_process_time

        # Process accumulated movements if enough time has passed
        if time_delta >= 0.016:  # ~60fps
            x = self.accumulated_x
            y = self.accumulated_y
            
            # Reset accumulators
            self.accumulated_x = 0
            self.accumulated_y = 0
            self.last_process_time = current_time
            
            # Apply threshold to reduce jitter
            if abs(x) < MOVEMENT_THRESHOLD:
                x = 0
            if abs(y) < MOVEMENT_THRESHOLD:
                y = 0
                
            return x, y
            
        return 0, 0

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
            width: 40px;
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
            width: 40px;
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
        let lastTwoFingerX = null;
        let threeFingerStartY = null;
        
        const twoFingerScrollSensitivity = 0.1;
        const mouseSensitivity = ${MOUSE_SENSITIVITY};
        const scrollSensitivity = ${SCROLL_SENSITIVITY};
        const SEND_INTERVAL = 10; // ~100fps
        let lastSendTime = 0;
        
        // Gesture settings
        const TAP_THRESHOLD = 150;
        const MOVE_THRESHOLD = 1;
        const THREE_FINGER_SWIPE_THRESHOLD = 50;
        const THREE_FINGER_VERTICAL_THRESHOLD = 50; // Minimum pixels for vertical three-finger gesture
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
            if (eventQueue.length > 0 && now - lastEventTime >= 1) {
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
            const now = performance.now();
            if (now - lastSendTime >= SEND_INTERVAL) {
                if (ws?.readyState === WebSocket.OPEN && ws.bufferedAmount === 0) {
                    ws.send(JSON.stringify(event));
                    lastSendTime = now;
                }
            }
        }

        function createTouchFeedback(x, y) {
            const feedback = document.createElement('div');
            feedback.className = 'touch-feedback';
            feedback.style.left = x + 'px';
            feedback.style.top = y + 'px';
            document.body.appendChild(feedback);
            setTimeout(() => feedback.remove(), 100);
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
                const currentX = (touch1.clientX + touch2.clientX) / 2;
                
                if (lastTwoFingerY !== null && lastTwoFingerX !== null) {
                    const deltaY = -1 * (currentY - lastTwoFingerY) * twoFingerScrollSensitivity;
                    const deltaX = (currentX - lastTwoFingerX) * twoFingerScrollSensitivity;
                    queueEvent({type: 'scroll', x: deltaX, y: deltaY});
                }
                
                lastTwoFingerY = currentY;
                lastTwoFingerX = currentX;
                
                // Create touch feedback for both fingers
                createTouchFeedback(touch1.clientX, touch1.clientY);
                createTouchFeedback(touch2.clientX, touch2.clientY);
            }
            else if (numTouches === 3) {
                const touches = Array.from(e.touches);
                if (!threeFingerStartX) {
                    threeFingerStartX = (touches[0].clientX + touches[1].clientX + touches[2].clientX) / 3;
                    threeFingerStartY = (touches[0].clientY + touches[1].clientY + touches[2].clientY) / 3;
                } else {
                    const currentX = (touches[0].clientX + touches[1].clientX + touches[2].clientX) / 3;
                    const currentY = (touches[0].clientY + touches[1].clientY + touches[2].clientY) / 3;
                    
                    // Calculate horizontal and vertical movement
                    const swipeDistanceX = currentX - threeFingerStartX;
                    const swipeDistanceY = currentY - threeFingerStartY;
                    
                    // Check which direction had more movement
                    if (Math.abs(swipeDistanceX) > Math.abs(swipeDistanceY)) {
                        // Horizontal swipe
                        if (Math.abs(swipeDistanceX) > THREE_FINGER_SWIPE_THRESHOLD) {
                            queueEvent({type: 'nextWindow'});
                            threeFingerStartX = currentX;
                            threeFingerStartY = currentY;
                        }
                    } else {
                        // Vertical swipe
                        if (Math.abs(swipeDistanceY) > THREE_FINGER_VERTICAL_THRESHOLD) {
                            queueEvent({
                                type: 'verticalGesture',
                                direction: swipeDistanceY > 0 ? 'down' : 'up'
                            });
                            threeFingerStartX = currentX;
                            threeFingerStartY = currentY;
                        }
                    }
                }
            }
        }

        function handleScrollbarTouch(e) {
            const touch = e.touches[0];
            const touchId = touch.identifier;
            const prevTouch = lastTouches[touchId];
            
            if (prevTouch) {
                const deltaY = 10 * (touch.clientY - prevTouch.clientY) * scrollSensitivity;
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
                threeFingerStartY = null;
                lastTouches = {};
                lastTwoFingerY = null;
                lastTwoFingerX = null;
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
    ws = web.WebSocketResponse(timeout=1, heartbeat=0.5)  # Add heartbeat to keep connection alive
    await ws.prepare(request)
    
    movement_buffer = MovementBuffer()
    event_queue = deque(maxlen=MAX_QUEUE_SIZE)
    process_task = None

    async def process_events():
        while True:
            try:
                if event_queue:
                    event = event_queue.popleft()
                    
                    if event['type'] == 'move':
                        movement_buffer.add_movement(event['x'], event['y'])
                        x, y = movement_buffer.get_smooth_movement()
                        if x != 0 or y != 0:
                            pyautogui.moveRel(x, y, duration=0)
                    
                    elif event['type'] == 'scroll':
                        scroll_y = int(event['y'] * -60)
                        scroll_x = int(event['x'] * -60)
                        if scroll_y != 0:
                            windll.user32.mouse_event(0x0800, 0, 0, scroll_y, 0)
                        if scroll_x != 0:
                            windll.user32.mouse_event(0x01000, 0, 0, scroll_x, 0)
                    
                    elif event['type'] == 'click':
                        pyautogui.click(button=event['button'])
                    
                    elif event['type'] == 'zoom':
                        if event['scale'] > 1:
                            pyautogui.hotkey('ctrl', '+')
                        else:
                            pyautogui.hotkey('ctrl', '-')
                    
                    elif event['type'] == 'nextWindow':
                        pyautogui.hotkey('alt', 'tab')

                    elif data['type'] == 'verticalGesture':
                        if data['direction'] == 'down':
                            pyautogui.hotkey('win', 'm')  # Windows+M minimizes all windows
                        else:  # direction is 'up'
                            pyautogui.hotkey('win', 'shift', 'm')  # Windows+Shift+M restores all windows
                
                await asyncio.sleep(0.016)  # Cap at ~60fps
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error processing events: {e}")
                await asyncio.sleep(0.1)

    
    try:
        # Start the event processing task
        process_task = asyncio.create_task(process_events())

        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    event_queue.append(data)
                except json.JSONDecodeError:
                    continue
    finally:
        process_task.cancel()
        try:
            await process_task
        except asyncio.CancelledError:
            pass

    return ws

async def index_handler(request):
    html = MOBILE_HTML.replace(
        '${MOUSE_SENSITIVITY}', str(MOUSE_SENSITIVITY)
    ).replace(
        '${SCROLL_SENSITIVITY}', str(SCROLL_SENSITIVITY)
    )
    return web.Response(text=html, content_type='text/html')

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
    
    try:
        await site.start()
        await asyncio.Event().wait()  # Keeps the server running
    finally:
        print("Shutting down server...")
        await runner.cleanup()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped")
        sys.exit(0)