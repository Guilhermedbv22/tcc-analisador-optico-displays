// Compilação e execução da lógica real do .ino com periféricos falsos.
// Não substitui Arduino-ESP32, temporização física ou ensaio de bancada.
#include <iostream>
#include <string>
#include "../firmware/iris_esp32/iris_esp32.ino"
int main() {
  setup();
  std::string line;
  while(std::getline(std::cin,line)) {
    Serial.out.clear();
    tratar(line.c_str());
    std::cout.write(Serial.out.data(),Serial.out.size());
    std::cout.flush();
  }
}
