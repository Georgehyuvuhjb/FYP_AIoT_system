# AIoT Smart Ward System (FYP)

An AI-powered Internet of Things (AIoT) system designed for smart healthcare and ward monitoring. This project integrates hardware sensors, an MQTT communication layer, a web dashboard, machine learning anomaly detection, and an LLM-based assistant.

## Demos

- **Software Demo**: [Watch on YouTube](https://youtu.be/IZissjhuDjo)
- **Hardware Demo**: [Watch on YouTube](https://youtu.be/fVWzUEaYzu0)

## Key Features

- **IoT Hardware Integration**: Microcontrollers collect sensor data and transmit it via MQTT.
- **Machine Learning Analysis**: Real-time anomaly detection to monitor patient behaviors (e.g., restroom usage duration based on pre-trained models).
- **LLM Assistant**: AI assistant integrated into the dashboard to query ward status and provide insights.
- **Web Dashboard**: A centralized user interface for staff to monitor real-time statuses and view ML predictions.

## Project Structure

- **Backend/**: Python-based server backend containing the web dashboard, MQTT client, ML prediction engine, and database manager.
- **Hardware/**: C++ (Arduino/ESP) code for the IoT edge devices.
- **Models/**: Pre-trained machine learning artifacts (Autoencoder, Isolation Forest, XGBoost).

## Quick Setup

### Backend (Software)
1. Navigate to the Backend folder.
2. Install dependencies: pip install -r requirements.txt
3. Setup Environment Variables: Create a .env file (refer to your own variables) and fill in your MQTT and LLM API keys.
4. Run the system: python web_app.py and python main.py

### Hardware
1. Open Hardware/maincode/combine/combine.ino in the Arduino IDE.
2. Copy secrets_example.h to secrets.h and fill in your Wi-Fi SSID, password, and MQTT credentials.
3. Flash the code to your microcontroller.
