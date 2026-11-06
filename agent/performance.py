"""P de PEAS: medida de desempenho.

Define o que é "agir bem". O agente é melhor quando:
  - mais carros passam (vazão)
  - menos tempo de espera acumulado
  - veículos de emergência esperam o mínimo possível (peso alto)
"""
from .environment import Intersection

W_THROUGHPUT = 1.0     # pontos por carro que passou
W_WAIT = 0.1           # penalidade por tick de espera de cada carro
W_EMERGENCY = 5.0      # penalidade por tick de espera de veículo de emergência


class Performance:
    def __init__(self):
        self.throughput = 0
        self.total_wait = 0        # soma de (carros na fila) a cada tick
        self.max_queue = 0
        self.switches = 0
        self.emergency_wait = 0    # soma da espera dos veículos de emergência que passaram
        self.emergency_passed = 0
        self.max_emergency_wait = 0

    def record_switch(self):
        self.switches += 1

    def update(self, env: Intersection):
        for car in env.departed:
            self.throughput += 1
            if car.emergency:
                self.emergency_passed += 1
                self.emergency_wait += car.waited
                self.max_emergency_wait = max(self.max_emergency_wait, car.waited)
        waiting = sum(len(q) for q in env.queues.values())
        self.total_wait += waiting
        self.max_queue = max(self.max_queue, max(len(q) for q in env.queues.values()))

    def score(self):
        return (W_THROUGHPUT * self.throughput
                - W_WAIT * self.total_wait
                - W_EMERGENCY * self.emergency_wait)

    def metrics(self):
        return {
            "score": round(self.score(), 1),
            "throughput": self.throughput,
            "total_wait": self.total_wait,
            "avg_wait": round(self.total_wait / self.throughput, 1) if self.throughput else 0,
            "max_queue": self.max_queue,
            "switches": self.switches,
            "emergency_passed": self.emergency_passed,
            "max_emergency_wait": self.max_emergency_wait,
        }
