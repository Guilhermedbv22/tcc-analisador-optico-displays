#pragma once
constexpr int WIFI_OFF=0;
struct WiFiMock{void mode(int){}};
inline WiFiMock WiFi;
