from machine import Pin, I2C
import network
import socket
import time
import dht
import ntptime
import ssd1306
import math
import os

# ================= OLED =================
i2c = I2C(0, scl=Pin(22), sda=Pin(21))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

# ================= DHT =================
dht_sensor = dht.DHT11(Pin(4))

# ================= WiFi =================
SSID = "Freebox-1C50BE"
PASSWORD = "6f4tcqknknq53r96qtzmv4"
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASSWORD)
while not wlan.isconnected():
    time.sleep(0.5)
print("Connected, IP:", wlan.ifconfig()[0])

# ================= Time =================
ntptime.settime()
GMT_OFFSET = 3600

# ================= CSV =================
if "data.csv" not in os.listdir():
    with open("data.csv", "w") as f:
        f.write("Timestamp,Temperature,Humidity,RSSI\n")

# ================= Helpers =================
def timestamp():
    t = time.localtime(time.time() + GMT_OFFSET)
    return "%04d-%02d-%02d %02d:%02d:%02d" % t[:6]

def read_dht_valid():
    for _ in range(5):
        try:
            dht_sensor.measure()
            t = dht_sensor.temperature()
            h = dht_sensor.humidity()
            return t, h
        except:
            time.sleep(0.2)
    return math.nan, math.nan

def oled_update(t, h, active):
    rssi = wlan.status('rssi')
    oled.fill(0)
    oled.text("MODE: ACTIVE" if active else "MODE: SLEEP", 0, 0)
    if active and not math.isnan(t) and not math.isnan(h):
        oled.text("T: %.1f C" % t, 0, 20)
        oled.text("H: %.0f %%" % h, 0, 30)
        oled.text("RSSI: %d dBm" % rssi, 0, 45)
    else:
        oled.text("No data", 0, 30)
        oled.text("RSSI: %d dBm" % rssi, 0, 45)
    oled.show()

# ================= HTML =================
html_page = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body { display:flex; flex-direction:row; font-family: sans-serif; }
#chart-container { flex:2; }
#oled-container { flex:1; margin-left:20px; }
</style>
</head>
<body>
<div id="chart-container">
<h2>ESP32 DHT Server</h2>
<p>WiFi RSSI: <span id="rssi">0</span> dBm</p>
<canvas id="chart" width="400" height="200"></canvas>
<p><a href="/download">Télécharger CSV</a></p>
</div>
<div id="oled-container">
<h3>OLED Snapshot</h3>
<img id="oled" src="/oled.png" width="128" height="64">
</div>
<script>
let ctx = document.getElementById('chart').getContext('2d');
let chart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            {label:'Temperature (C)', data:[], borderColor:'red', fill:false},
            {label:'Humidity (%)', data:[], borderColor:'blue', fill:false}
        ]
    },
    options: {animation:false, responsive:true, scales:{x:{title:{display:true,text:'Time'}},y:{beginAtZero:true}}}
});
function updateData(){
    fetch('/temperature').then(r=>r.text()).then(t=>{
        fetch('/humidity').then(r=>r.text()).then(h=>{
            fetch('/rssi').then(rssi_res=>rssi_res.text()).then(rssi=>{
                document.getElementById('rssi').innerHTML = rssi;
                let time = new Date().toLocaleTimeString();
                chart.data.labels.push(time);
                chart.data.datasets[0].data.push(parseFloat(t) || 0);
                chart.data.datasets[1].data.push(parseFloat(h) || 0);
                if(chart.data.labels.length>20){
                    chart.data.labels.shift();
                    chart.data.datasets[0].data.shift();
                    chart.data.datasets[1].data.shift();
                }
                chart.update();
                document.getElementById('oled').src = '/oled.png?ts=' + new Date().getTime();
            });
        });
    });
}
setInterval(updateData, 1000);
</script>
</body>
</html>
"""

# ================= Server =================
s = socket.socket()
s.bind(("", 80))
s.listen(1)
print("Server ready")

ACTIVE_INTERVAL = 5000
SLEEP_INTERVAL = 8000
READ_INTERVAL = 500

active_mode = True
mode_start = time.ticks_ms()
last_temp = math.nan
last_hum = math.nan

while True:
    now = time.ticks_ms()

    # ===== ACTIVE MODE =====
    if active_mode:
        if time.ticks_diff(now, mode_start) < ACTIVE_INTERVAL:
            last_temp, last_hum = read_dht_valid()
            oled_update(last_temp, last_hum, True)
            rssi_val = wlan.status('rssi')
            with open("data.csv", "a") as f:
                f.write("%s,%.1f,%.1f,%d\n" % (
                    timestamp(),
                    0 if math.isnan(last_temp) else last_temp,
                    0 if math.isnan(last_hum) else last_hum,
                    rssi_val
                ))
            time.sleep_ms(READ_INTERVAL)
        else:
            active_mode = False
            mode_start = now
            oled_update(0,0,False)
            print("=== SLEEP MODE ===")
    else:
        last_temp = 0
        last_hum = 0
        oled_update(0,0,False)
        if time.ticks_diff(now, mode_start) >= SLEEP_INTERVAL:
            active_mode = True
            mode_start = now
            print("=== ACTIVE MODE ===")

    # ===== Handle Web Requests =====
    try:
        conn, addr = s.accept()
        request = conn.recv(1024).decode('utf-8')
        if "GET /download" in request:
            try:
                conn.send("HTTP/1.0 200 OK\r\nContent-Type: text/csv\r\nContent-Disposition: attachment; filename=data.csv\r\n\r\n")
                with open("data.csv","r") as f:
                    for line in f:
                        conn.send(line.encode())
            except:
                conn.send("HTTP/1.0 404 Not Found\r\n\r\nCSV file not found")
        elif "GET /oled.png" in request:
            try:
                with open("oled_placeholder.png","rb") as f:
                    conn.send("HTTP/1.0 200 OK\r\nContent-Type: image/png\r\n\r\n".encode())
                    conn.send(f.read())
            except:
                conn.send("HTTP/1.0 404 Not Found\r\n\r\nImage not found".encode())
        elif "GET /temperature" in request:
            conn.send("HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\n".encode())
            conn.send(str(last_temp).encode())
        elif "GET /humidity" in request:
            conn.send("HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\n".encode())
            conn.send(str(last_hum).encode())
        elif "GET /rssi" in request:
            conn.send("HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\n".encode())
            conn.send(str(wlan.status('rssi')).encode())
        else:
            conn.send(("HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n"+html_page).encode())
        conn.close()
    except:
        pass

