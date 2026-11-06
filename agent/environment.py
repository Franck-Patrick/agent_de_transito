"""E de PEAS: o ambiente.

Um cruzamento de 4 vias (N, S, E, W) com semáforo de 2 fases:
  - eixo NS (norte e sul passam juntos)
  - eixo EW (leste e oeste passam juntos)

O ambiente NÃO decide nada: ele só guarda o estado do mundo (filas e sinal) e
avança o tempo em ticks. Quem muda o sinal é o atuador, a pedido do agente.
"""
import random
from dataclasses import dataclass

DIRECTIONS = ("N", "S", "E", "W")
AXIS_OF = {"N": "NS", "S": "NS", "E": "EW", "W": "EW"}
OTHER_AXIS = {"NS": "EW", "EW": "NS"}

YELLOW_TICKS = 2          # duração do amarelo
DEPART_EVERY = 2          # com verde, sai 1 carro a cada 2 ticks por via
DEFAULT_ARRIVAL_PROB = 0.12   # chance de chegar 1 carro por tick em cada via
SURGE_ARRIVAL_PROB = 0.35     # chance durante um pico de tráfego


@dataclass
class Car:
    id: int
    emergency: bool = False
    waited: int = 0       # ticks que passou parado na fila


@dataclass
class Signal:
    axis: str = "NS"      # eixo que está (ou estava, se em amarelo) com o verde
    phase: str = "GREEN"  # GREEN ou YELLOW
    phase_time: int = 0   # ticks desde que a fase começou


class Intersection:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.tick = 0
        self.signal = Signal()
        self.queues = {d: [] for d in DIRECTIONS}
        self.arrival_prob = {d: DEFAULT_ARRIVAL_PROB for d in DIRECTIONS}
        self.departed = []    # carros que saíram no último tick
        self._next_id = 1

    # --- mudanças feitas de fora (atuador e eventos) ---

    def start_yellow(self):
        """Inicia a troca: o verde atual vai para amarelo e depois o outro eixo abre."""
        if self.signal.phase == "GREEN":
            self.signal.phase = "YELLOW"
            self.signal.phase_time = 0

    def add_car(self, direction, emergency=False):
        car = Car(id=self._next_id, emergency=emergency)
        self._next_id += 1
        if emergency:
            # simplificação: o veículo de emergência fura a fila
            self.queues[direction].insert(0, car)
        else:
            self.queues[direction].append(car)
        return car

    # --- passagem do tempo ---

    def step(self):
        self.tick += 1
        self.departed = []
        self._arrivals()
        self._advance_signal()
        self._departures()
        self._age_cars()

    def _arrivals(self):
        for d in DIRECTIONS:
            if self.rng.random() < self.arrival_prob[d]:
                self.add_car(d)

    def _advance_signal(self):
        s = self.signal
        s.phase_time += 1
        if s.phase == "YELLOW" and s.phase_time >= YELLOW_TICKS:
            s.axis = OTHER_AXIS[s.axis]
            s.phase = "GREEN"
            s.phase_time = 0

    def _departures(self):
        s = self.signal
        if s.phase != "GREEN" or s.phase_time < 1:
            return
        for d in DIRECTIONS:
            if AXIS_OF[d] != s.axis or not self.queues[d]:
                continue
            front = self.queues[d][0]
            if front.emergency or s.phase_time % DEPART_EVERY == 1:
                self.departed.append(self.queues[d].pop(0))

    def _age_cars(self):
        for q in self.queues.values():
            for car in q:
                car.waited += 1
