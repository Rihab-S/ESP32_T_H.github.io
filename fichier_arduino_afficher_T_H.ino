#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <WiFi.h>
#include <ESPAsyncWebServer.h>
#include <DHT.h>
#include "SPIFFS.h"
#include <time.h>

// ================= OLED =================
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// ================= DHT =================
#define DHTPIN 4
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

// ================= WiFi =================
const char* ssid = "ajouter le nom de votre wifi";
const char* password = "ajouter le mot de passe";

// ================= Server =================
AsyncWebServer server(80);

// ================= Time =================
const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 3600;
const int daylightOffset_sec = 0;

// ================= Timing =================
const unsigned long MEASURE_INTERVAL = 2 * 60 * 1000UL; // 2 minutes = cycle complet
const unsigned long ACTIVE_DURATION  = 1 * 60 * 1000UL; // 1 minute Active

unsigned long previousMillis = 0;
bool activeMode = false;

// ================= Shared Sensor Values =================
float lastTemperature = NAN;
float lastHumidity    = NAN;

// ================= HTML =================
const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE HTML><html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://use.fontawesome.com/releases/v5.7.2/css/all.css">
<style>
html{font-family:Arial;text-align:center;}
h2{font-size:3rem;}
p{font-size:3rem;}
.units{font-size:1.2rem;}
.download-btn{
 font-size:1.5rem;
 padding:10px 20px;
 background:#059e8a;
 color:white;
 border-radius:5px;
 text-decoration:none;
}
</style>
</head>

<body>
<h2>ESP32 DHT Server</h2>

<div id="activeBlock">
<p>
<i class="fas fa-thermometer-half"></i>
Temperature: <span id="temperature">--</span>
<sup class="units">&deg;C</sup>
</p>

<p>
<i class="fas fa-tint"></i>
Humidity: <span id="humidity">--</span>
<sup class="units">&percnt;</sup>
</p>
</div>

<div id="sleepBlock" style="display:none;">
<h2>Sleep Mode</h2>
</div>

<a href="/data.csv" class="download-btn" download>Download CSV</a>

<script>
function updateMode(){
 fetch("/mode").then(r=>r.text()).then(m=>{
  document.getElementById("activeBlock").style.display =
   (m==="ACTIVE")?"block":"none";
  document.getElementById("sleepBlock").style.display =
   (m==="SLEEP")?"block":"none";
 });
}

function updateData(){
 fetch("/temperature").then(r=>r.text())
  .then(t=>document.getElementById("temperature").innerHTML=t);
 fetch("/humidity").then(r=>r.text())
  .then(h=>document.getElementById("humidity").innerHTML=h);
}

setInterval(updateMode,2000);
setInterval(updateData,5000);
</script>
</body>
</html>
)rawliteral";

// ================= Helpers =================
float readTemperature(){
 float t=dht.readTemperature();
 return isnan(t)?NAN:t;
}

float readHumidity(){
 float h=dht.readHumidity();
 return isnan(h)?NAN:h;
}

String getTimestamp(){
 struct tm timeinfo;
 if(!getLocalTime(&timeinfo)) return "0000-00-00 00:00:00";
 char buf[20];
 strftime(buf,sizeof(buf),"%Y-%m-%d %H:%M:%S",&timeinfo);
 return String(buf);
}

void updateOLED(float t,float h,bool active){
 display.clearDisplay();
 display.setTextSize(2);
 display.setTextColor(WHITE);
 display.setCursor(0,0);

 if(active){
  display.print("Active Mode");
  display.setCursor(0,20);
  display.print("T:");display.print(t,1);display.print("C");
  display.setCursor(0,40);
  display.print("H:");display.print(h,0);display.print("%");
 }else{
  display.print("Sleep Mode");
 }
 display.display();
}

// ================= Setup =================
void setup(){
 Serial.begin(115200);
 dht.begin();

 if(!display.begin(SSD1306_SWITCHCAPVCC,0x3C)){
  while(true);
 }

 SPIFFS.begin(true);
 if(!SPIFFS.exists("/data.csv")){
  File f=SPIFFS.open("/data.csv",FILE_WRITE);
  f.println("Timestamp,Temperature,Humidity");
  f.close();
 }

 WiFi.begin(ssid,password);
 while(WiFi.status()!=WL_CONNECTED) delay(500);

 configTime(gmtOffset_sec,daylightOffset_sec,ntpServer);

 server.on("/",HTTP_GET,[](AsyncWebServerRequest *r){
  r->send_P(200,"text/html",index_html);
 });

 server.on("/mode",HTTP_GET,[](AsyncWebServerRequest *r){
  r->send(200,"text/plain",activeMode?"ACTIVE":"SLEEP");
 });

 server.on("/temperature",HTTP_GET,[](AsyncWebServerRequest *r){
  if(activeMode && !isnan(lastTemperature))
   r->send(200,"text/plain",String(lastTemperature));
  else
   r->send(200,"text/plain","--");
 });

 server.on("/humidity",HTTP_GET,[](AsyncWebServerRequest *r){
  if(activeMode && !isnan(lastHumidity))
   r->send(200,"text/plain",String(lastHumidity));
  else
   r->send(200,"text/plain","--");
 });

 server.on("/data.csv",HTTP_GET,[](AsyncWebServerRequest *r){
  r->send(SPIFFS,"/data.csv","text/csv");
 });

 server.begin();

 previousMillis=millis();
 updateOLED(0,0,false);
}

// ================= Loop =================
void loop(){
 unsigned long now=millis();

 if(now-previousMillis>=MEASURE_INTERVAL){
  previousMillis=now;
  activeMode=true;

  // ===== SINGLE SENSOR READ =====
  lastTemperature = readTemperature();
  lastHumidity    = readHumidity();

  updateOLED(lastTemperature,lastHumidity,true);

  File f=SPIFFS.open("/data.csv",FILE_APPEND);
  if(f){
   f.println(getTimestamp()+","+String(lastTemperature)+","+String(lastHumidity));
   f.close();
  }

  delay(ACTIVE_DURATION);

  activeMode=false;
  updateOLED(0,0,false);
 }
}
