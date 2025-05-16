# Importam bibliotecile necesare
import cv2                          # Pentru procesarea imaginilor
import numpy as np                  # Pentru manipularea datelor de imagine
import pyzbar.pyzbar as pyzbar      # Pentru citirea codurilor QR
import urllib.request               # Pentru descarcarea imaginilor de la ESP32-CAM
import tkinter as tk                # Pentru interfata grafica
from PIL import Image, ImageTk      # Pentru afisarea imaginilor in interfata grafica
import threading                    # Pentru masurarea timpului (expirare cod QR, timer)
import time                         # Pentru a lucra cu timpul

ALLOWED_DURATION = 10               # Cate secunde ramane bariera deschisa
QR_EXPIRY_SECONDS = 30              # Codurile QR expira dupa 30 de secunde
plate_db_file = 'plates.txt'        # Fisierul cu numerele de inmatriculare si codurile secrete
url = 'http://192.168.4.1/cam-hi.jpg'  # Link-ul de la camera ESP32-CAM
servo_url = 'http://192.168.4.1/set-servo?open='    # Link-ul pentru a deschide/inchide servo motorul

allowed = False             # Stocheaza daca un cod QR este valid (adevarat sau fals)
status_open = False         # Stocheaza daca bariera este deschisa sau inchisa
qr_data = "-"               # Stocheaza datele codului QR curent
countdown = 0               # Timpul ramas pentru bariera deschisa
lock = threading.Lock()     # Asigura accesul sigur la date pana cand sunt mai multe thread-uri

def load_plates():
    # Citeste fisierul plates.txt si salveaza numerele de inmatriculare si codurile intr-un dictionar
    # Formatul fisierului plates.txt: NUMAR_INMATRICULARE,COD
    try:
        with open(plate_db_file, 'r') as f:
            return {
                line.strip().split(",")[0].upper(): line.strip().split(",")[1]
                for line in f if "," in line
            }
    except:
        return {}

# Dictionarul final cu numerele de inmatriculare
valid_plates = load_plates()

# Functia trimite comanda catre ESP32-CAM pentru a deschide sau inchide servo motorul
# open_state = True pentru a deschide, False pentru a inchide
def sync_servo(open_state):
    try:
        urllib.request.urlopen(servo_url + ('1' if open_state else '0'))
    except:
        print("ESP32 not reachable or servo sync failed")

# Functia care porneste un timer pentru a inchide bariera dupa un anumit timp
# Foloseste un thread separat pentru a nu bloca interfata grafica
def start_timer():
    global countdown, status_open, allowed
    with lock:
        if countdown == 0:
            countdown = ALLOWED_DURATION
            status_open = True
            sync_servo(True)
            threading.Thread(target=timer_thread, daemon=True).start()

# Functia care scade timpul ramas si inchide bariera
# Daca timpul ajunge la 0, bariera se inchide
def timer_thread():
    global countdown, status_open, allowed
    while countdown > 0:
        time.sleep(1)
        with lock:
            countdown -= 1
    with lock:
        status_open = False
        allowed = False
        sync_servo(False)

# Functia care deschide bariera manual
# Aceasta functie este apelata de butonul "Force Open" din interfata grafica
def force_open():
    global allowed
    with lock:
        allowed = True
    start_timer()

# Functia care actualizeaza interfata grafica
# Aceasta functie este apelata la fiecare 100ms
def update_gui():
    #Actualizeaza imaginea camerei, citeste codul QR si actualizeaza interfata grafica
    global qr_data, allowed, status_open, countdown
    ret, frame = get_frame() # Preluam imaginea de la camera
    if ret:
        # Cautam coduri QR in imagine
        decoded_objects = pyzbar.decode(frame)
        current_qr = "-"
        for obj in decoded_objects:
            current_qr = obj.data.decode("utf-8")
            break # Luam primul QR detectat
        
        # Daca QR-ul este nou
        if current_qr != "-" and current_qr != qr_data:
            try:
                # Separam codul in componentele sale
                plate, code, ts_str = current_qr.split("|")
                plate = plate.upper()
                ts = int(ts_str)
                now = int(time.time())

                # Verificam daca QR-ul este valid
                if (
                    now - ts <= QR_EXPIRY_SECONDS and   # Verificam daca QR-ul nu a expirat
                    plate in valid_plates and           # Verificam daca numarul de inmatriculare este in baza de date
                    valid_plates[plate] == code         # Verificam daca codul secret este corect
                ):
                    allowed = True
                    start_timer()
                    print(f"✅ Valid QR: {plate}")
                else:
                    allowed = False
                    print("❌ Invalid or expired QR")
            except Exception as e:
                print("⚠️ QR Parse Error:", e)
                allowed = False

            qr_data = current_qr
        elif current_qr == "-":
            qr_data = "-"

        # Convertim imaginea in formatul corect pentru interfata grafica
        # si o afisam
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(img)
        imgtk = ImageTk.PhotoImage(image=img)
        video_label.imgtk = imgtk
        video_label.configure(image=imgtk)

        # Actualizam textul de pe ecran
        qr_label.config(text=f"QR: {qr_data}")
        status_label.config(
            text="Status: OPEN" if status_open else "Status: CLOSED",
            fg="lime" if status_open else "red"
        )
        allowed_label.config(
            text=f"Allowed: {'YES' if allowed else 'NO'}",
            fg="lime" if allowed else "red"
        )
        timer_label.config(text=f"Timer: {countdown}s" if countdown > 0 else "Timer: -")

    # Programam sa se repete la fiecare 100ms
    root.after(100, update_gui)

def get_frame():
    # Preia imaginea de la camera ESP32-CAM
    try:
        img_resp = urllib.request.urlopen(url)
        imgnp = np.array(bytearray(img_resp.read()), dtype=np.uint8)
        frame = cv2.imdecode(imgnp, -1)
        return True, frame
    except:
        return False, None

# Configurarea interfetei grafice
root = tk.Tk()                          # Creaza fereastra principala
root.title("PROIECT MEA")               # Titlul ferestrei   
root.configure(bg="#1e1e1e")

# Titlul aplicatiei
title = tk.Label(root, text="Bariera ESP32-CAM", font=("Segoe UI", 18, "bold"), bg="#1e1e1e", fg="white")
title.pack(pady=10)

# Ethicheta unde va fi afisata imaginea live
video_label = tk.Label(root, bg="#1e1e1e")
video_label.pack()

# Informatii despre statusul sistemului (QR, status, timer)
info_frame = tk.Frame(root, bg="#1e1e1e")
info_frame.pack(pady=15)

qr_label = tk.Label(info_frame, text="QR: -", font=("Segoe UI", 12), bg="#1e1e1e", fg="white")
qr_label.grid(row=0, column=0, padx=20)

status_label = tk.Label(info_frame, text="Status: CLOSED", font=("Segoe UI", 12), bg="#1e1e1e", fg="red")
status_label.grid(row=0, column=1, padx=20)

allowed_label = tk.Label(info_frame, text="Allowed: NO", font=("Segoe UI", 12), bg="#1e1e1e", fg="red")
allowed_label.grid(row=0, column=2, padx=20)

timer_label = tk.Label(info_frame, text="Timer: -", font=("Segoe UI", 12), bg="#1e1e1e", fg="white")
timer_label.grid(row=0, column=3, padx=20)

# Butonul pentru a deschide manual / fortat bariera
button_frame = tk.Frame(root, bg="#1e1e1e")
button_frame.pack(pady=10)

force_btn = tk.Button(button_frame, text="Force Open", font=("Segoe UI", 12), bg="#0078D7", fg="white", command=force_open)
force_btn.pack(ipadx=10, ipady=5)

# Pornim procesul de actualizare a interfetei grafice
update_gui()

# Lasam aplicatia sa ruleze pana cand este inchisa manual
root.mainloop()
