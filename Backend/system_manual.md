# Smart Ward AIoT Toilet Safety System - Comprehensive User & Technical Manual

This manual explains the operation, hardware components, AI technology, and Standard Operating Procedures (SOP) for the "Smart Ward AIoT Toilet Safety System". It serves as the core knowledge base for system operators and the AI assistant.

---

## 1. System Overview
Designed specifically for hospital ward toilets, this system ensures patient safety without compromising privacy (no cameras used). By utilizing Internet of Things (IoT) hardware and Artificial Intelligence (AI), it monitors toilet occupancy and detects potential emergencies.

The core philosophy of this system is **"Abandoning Fixed Time Limits."** Instead of a universal 20-minute limit for all patients, the system uses an AI model to calculate a personalized, **"Dynamic Safety Threshold"** based on each patient's age, mobility, and medical history.

---

## 2. Hardware & Interfaces
The hardware is installed at the toilet entrance, driven by an ESP32 microcontroller:

*   **RFID Reader (MFRC522)**: Patients must scan their assigned RFID wristband or card to check in and out. This is the sole method for the system to identify the user.
*   **LCD Display**:
    *   Normally displays: "Scan Card...".
    *   During use: "Occupied" along with the remaining safety time countdown.
*   **Smart Servo Motor (Door Lock)**: Controls the physical door. In an emergency, the system automatically opens the door to allow immediate access for medical staff.
*   **Multi-function Physical Button**:
    *   **Short Press (Extend Time)**: Automatically adds 5 minutes to the safety countdown if the patient needs more time.
    *   **Long Press for 3 Seconds (Manual SOS)**: Immediately triggers the highest-level emergency alarm (`ACCIDENT`).
*   **Audio Speaker (I2S)**: Plays different voice prompts for warnings (time is almost up) and emergencies.

---

## 3. Web Dashboard & Management
The central hub for monitoring and configuration is a sleek, dual-column web interface accessible by medical staff:

*   **Live Monitoring Dashboard**:
    *   **Left Column (Currently In Use)**: A real-time table displaying which toilets are occupied, who is inside, when they entered, and their AI-calculated time limit.
    *   **Right Column (Incident Alerts)**: Only displays rooms that have triggered a `WARNING` or `ACCIDENT` state, requiring immediate attention.
*   **Data Management**: A separate section for staff to register new RFID cards, create patient profiles, and link cards to patients.
*   **Recent Event Logs**: A continuous scrolling log at the bottom showing the latest entries, exits, and system events.
*   **AI Assistant**: A floating chat widget in the corner powered by an LLM (Large Language Model) integrated with real-time RAG (Retrieval-Augmented Generation), ready to answer operational questions.

---

## 4. System States & SOP (Standard Operating Procedures)
The system operates in one of four states. Staff should respond according to the following SOPs:

### State 1: IDLE
*   **Description**: Toilet is vacant. LED is off, LCD shows "Scan Card".
*   **SOP**: None.

### State 2: USER INSIDE (Occupied)
*   **Description**: Patient has scanned in. The system is counting down based on the AI-calculated threshold. LED is on.
*   **SOP**: Monitor via the Web Dashboard if needed. No direct action required.

### State 3: WARNING
*   **Description**: The patient has exceeded their safe time limit. The hardware plays an audio reminder: "If you are still inside, please press the button to extend your time."
*   **SOP**: The Dashboard displays an orange alert. If the patient does not press the physical button to extend within 3 minutes, the state escalates to an Emergency. Staff may choose to perform a proactive wellness check.

### State 4: ACCIDENT / EMERGENCY 🚨
*   **Triggers**:
    1. Warning state persists for over 3 minutes with no patient response.
    2. Patient manually long-presses the physical button for 3 seconds.
*   **System Action**:
    *   Hardware plays a loud, looping emergency siren.
    *   **The toilet door automatically unlocks and opens.**
    *   The Web Dashboard displays a flashing red alert.
*   **SOP**:
    1.  **Highest Priority**: Medical staff must immediately proceed to the toilet to verify the patient's condition.
    2.  Once safe, physical reset the system or click "Acknowledge" on the Dashboard.

---

## 5. How the AI Dynamic Threshold Works
The AI module (`ai_predictor.py`) uses Machine Learning techniques known as "Anomaly Detection". **The system is capable of utilizing three different models, selected via configuration:**
1.  **One-Class SVM**
2.  **Isolation Forest**
3.  **Simple Autoencoder**

### Calculation Basis (Input Features)
When a card is scanned, the system fetches the patient's health profile (`hospital_iot.db`), which includes:
*   **Age**
*   **Gender**
*   **Mobility Level**: (0 = No issue, 1 = Needs aid, 2 = Cannot move independently)
*   **Has Gastro Issue**: (Yes/No) Patients with gastrointestinal issues safely require more time.
*   **Has Uro Issue**: (Yes/No)
*   **Self-Reported Max Seconds**: The time the patient believes they typically need.

### The Calculation Process
1.  The system inputs these features into the selected AI model and simulates different toilet durations (starting from 0 seconds and increasing).
2.  For each simulated second, the AI outputs an "Anomaly Score".
3.  As the simulated duration extends, the score will eventually cross a pre-determined risk boundary, indicating that staying this long is "highly unusual" or "anomalous" for this specific patient.
4.  The system records this exact crossover point as the patient's unique "Dynamic Safety Threshold".
5.  This entire calculation takes milliseconds upon card scan and is instantly sent to the ESP32 hardware via MQTT to start the countdown.

---

## 6. Frequently Asked Questions (FAQ)

**Q: What happens if the Wi-Fi/Network disconnects?**
A: The ESP32 hardware will lose connection to the Dashboard. However, it possesses a built-in failsafe mechanism. If disconnected, it defaults to a hard-coded absolute maximum limit (e.g., 20 minutes) and will still independently trigger the local audio alarm and open the door if that limit is reached.

**Q: What if a patient forgets their RFID card?**
A: The current design requires an initial RFID scan to activate the protective countdown mechanism. Without a scan, the system remains IDLE. It is highly recommended to integrate the RFID chip directly into the patient's standard hospital wristband.

**Q: Why do some patients receive very short time limits?**
A: If the AI evaluates a patient as having extremely poor mobility (Level = 1) and no specific excretory issues, it determines that leaving them unattended in a bathroom for extended periods is an extreme fall risk. Therefore, it deliberately shortens the threshold to prompt an earlier wellness check from the nursing staff.
