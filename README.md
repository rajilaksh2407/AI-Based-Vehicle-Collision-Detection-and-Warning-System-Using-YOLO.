# AI-Based-Vehicle-Collision-Detection-and-Warning-System-Using-YOLO.
📌 Overview

The AI-Based Vehicle Collision Detection and Warning System Using YOLO is a computer vision-based safety system designed to detect vehicles and other objects in real time and provide an early warning when an object enters a predefined danger/safe zone.
The system uses the YOLO (You Only Look Once) object detection algorithm along with OpenCV to identify objects from a live camera feed or video. It estimates the distance between the detected object and the camera and triggers a warning when the object gets dangerously close.

🛠️ Technologies Used
	
Python

YOLO

OpenCV	

Flask	

SQLite	

HTML/CSS/JavaScript	

NumPy

📂 Project Structure

AI-Based-Vehicle-Collision-Detection-and-Warning-System-Using-YOLO/
│
├── app.py
├── requirements.txt
├── README.md
│
├── static/
│   ├── css/
│   └── js/
│
├── templates/
│   └── index.html
│
├── models/
│   └── YOLO model files
│
├── database/
│   └── warnings.db
│
└── utils/
    └── detection utilities

▶️ How to Run

1. Clone the Repository
git clone https://github.com/rajilaksh2407/AI-Based-Vehicle-Collision-Detection-and-Warning-System-Using-YOLO..git
2. Open the Project Folder
cd AI-Based-Vehicle-Collision-Detection-and-Warning-System-Using-YOLO.
3. Install Required Packages
pip install -r requirements.txt
4. Start the Application
python app.py
5. Access the System
http://127.0.0.1:5000/

🖥️ System Output

The system provides:

Detected object bounding boxes
Object labels
Approximate distance
Safe/danger zone indication
Collision warning
Audio alert
Warning/event logging

👩‍💻 Author

Rajalakshmi V

GitHub:
https://github.com/rajilaksh2407

