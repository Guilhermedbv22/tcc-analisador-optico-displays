#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cstdio>
#include <algorithm>
#include <string>
#include <cstdarg>
using std::min; using std::max;
constexpr int LOW=0,HIGH=1,OUTPUT=2,INPUT=3,ADC_11db=4;
inline int64_t fake_clock=0;
struct SerialMock {
  std::string out;
  void begin(uint32_t){}
  void print(const char* x){out+=x;}
  void println(const char* x){out+=x;out+='\n';}
  void printf(const char*fmt,...){char b[4096];va_list args;va_start(args,fmt);vsnprintf(b,sizeof(b),fmt,args);va_end(args);out+=b;}
  size_t write(const uint8_t*p,size_t n){out.append(reinterpret_cast<const char*>(p),n);return n;}
  void flush(){}
  int available(){return 0;}
  int read(){return -1;}
};
inline SerialMock Serial;
inline void digitalWrite(int,int){}
inline void pinMode(int,int){}
inline void delay(unsigned x){fake_clock+=1000*x;}
inline void delayMicroseconds(unsigned x){fake_clock+=x;}
inline uint16_t analogRead(int){fake_clock+=20;return 1234;}
inline uint32_t analogReadMilliVolts(int){fake_clock+=20;return 1000;}
inline void analogReadResolution(int){}
inline void analogSetPinAttenuation(int,int){}
inline void dacWrite(int,int){}
inline void dacDisable(int){}
