# Mobile Trackpad

Turn your mobile device into a wireless trackpad for your computer. This application creates a web server that allows you to control your computer's mouse cursor using your phone or tablet's touchscreen.

## Features

- Smooth cursor control with touch tracking
- Two-finger scrolling
- Three-finger swipe for Alt+Tab window switching
- Dedicated scroll bar for precise scrolling
- Zoom bar for quick Ctrl+/- zooming
- Tap to left-click
- Visual touch feedback
- Fullscreen mode support

## Requirements

- Python 3.7+
- A mobile device with a modern web browser
- Computer and mobile device on the same network

## Installation

1. Install the required Python packages using the requirements.txt file:
```bash
pip install -r requirements.txt
```

2. Download `mobile_trackpad.py` to your computer.

## Usage

1. Run the server:
```bash
python mobile_trackpad.py
```

2. The server will display a URL (e.g., `http://192.168.1.100:5000`)

3. On your mobile device:
   - Connect to the same network as your computer
   - Open the provided URL in your web browser
   - (Optional) Enable fullscreen mode for better experience

## Controls

| Gesture | Action |
|---------|--------|
| Single finger move | Move cursor |
| Tap | Left click |
| Two-finger slide | Scroll vertically |
| Three-finger swipe | Switch windows (Alt+Tab) |
| Right scroll bar | Precise scrolling |
| Bottom zoom bar | Zoom in/out (Ctrl +/-) |

## Configuration

Key sensitivity settings can be adjusted in the JavaScript code:
```javascript
const twoFingerScrollSensitivity = 0.3;
const mouseSensitivity = 3.5;
const scrollSensitivity = 1.0;
```

## Technical Details

- Uses aiohttp's WebSocket implementation for real-time communication
- Implements touch event throttling for performance
- Provides visual feedback for touch interactions
- Auto-reconnects if connection is lost
- Uses pyautogui for mouse control and keyboard shortcuts

## Troubleshooting

1. **Connection Issues**
   - Ensure both devices are on the same network
   - Check if firewall is blocking port 5000
   - Try using the IP address instead of localhost

2. **Performance Issues**
   - Close other browser tabs/applications
   - Reduce animation effects if needed
   - Check network latency

3. **Touch Not Working**
   - Enable touch events in your browser
   - Clear browser cache
   - Try a different browser

## Security Notes

- The server accepts connections from any device on the network
- No authentication is implemented by default
- Use in trusted networks only

## Limitations

- Cannot simulate right-click
- Zoom functionality limited to Ctrl+/- commands
- Requires continuous network connection
- Touch gestures may vary by device/browser

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is open source and available under the MIT License.