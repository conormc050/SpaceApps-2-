void setup() {
  Serial1.begin(9600);
  Serial1.println("READY 16 2");
  randomSeed(analogRead(A15));
}

void loop() {
  Serial1.print("Vhr=");
  Serial1.println(60 + random(0, 20));
  delay(1000);
}
