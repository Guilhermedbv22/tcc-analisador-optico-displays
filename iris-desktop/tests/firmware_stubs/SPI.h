#pragma once
#include "Arduino.h"
constexpr int MSBFIRST=1,SPI_MODE0=0;
struct SPISettings{uint32_t hz;SPISettings(uint32_t h,int,int):hz(h){}};
struct SPIMock{
 uint32_t hz=1000000;
 void begin(int,int,int,int){}
 void beginTransaction(SPISettings s){hz=s.hz;}
 void endTransaction(){}
 void transferBytes(uint8_t*,uint8_t*rx,int){fake_clock+=24000000/hz;rx[0]=0;rx[1]=4;rx[2]=210;}
};
inline SPIMock SPI;
