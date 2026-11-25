#pragma once
#include <stdint.h>

// Estado puro: testado em host; GPIOs e estabilização ficam no .ino.
// Ganho permanece constante entre ARMED e END.
namespace IrisGain {
constexpr double RF_BASE = 470000.0;
constexpr double BRANCH[3] = {52300.0, 127000.0, 412000.0};
inline double effective(uint8_t range, double ron=0.0) {
  if(range >= 3) return RF_BASE;
  const double r=BRANCH[range]+ron;
  return RF_BASE*r/(RF_BASE+r);
}
enum class Decision { TRY_NEXT, LOCKED, OUT_OF_RANGE, NO_SIGNAL, NO_CAPTURES };
struct Auto {
  bool active=false, locked=false;
  uint8_t range=0;
  int8_t last_good=-1;
  uint16_t target=3276, minimum=4095, maximum=0;
  uint32_t captures=0;
  void reset_observation() { minimum=4095; maximum=0; captures=0; }
  void start(uint16_t permille) {
    active=true; locked=false; range=0; last_good=-1;
    target=uint16_t((uint32_t(4095)*permille)/1000);
    reset_observation();
  }
  void observe(uint16_t lo, uint16_t hi) {
    if(!active || locked) return;
    if(lo<minimum) minimum=lo;
    if(hi>maximum) maximum=hi;
    ++captures;
  }
  Decision evaluate() {
    if(!captures) return Decision::NO_CAPTURES;
    // Não atribui a causa do zero. Exige variação mensurável nos pilotos.
    if(maximum-minimum < 20) { active=false; return Decision::NO_SIGNAL; }
    if(maximum>=target) {
      active=false;
      if(last_good<0) return Decision::OUT_OF_RANGE;
      range=uint8_t(last_good); locked=true; return Decision::LOCKED;
    }
    last_good=int8_t(range);
    if(range==3) { active=false; locked=true; return Decision::LOCKED; }
    ++range; reset_observation(); return Decision::TRY_NEXT;
  }
};
}
