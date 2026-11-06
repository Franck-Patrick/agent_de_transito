"""S de PEAS: sensores.

O agente nunca lê o ambiente direto. Ele só enxerga o que os sensores entregam:
  - laço indutivo por via: tamanho da fila e maior tempo de espera (pode falhar)
  - detector de sirene: vias com veículo de emergência
  - leitura do próprio semáforo
"""
from dataclasses import dataclass, asdict

from .environment import DIRECTIONS, Intersection


@dataclass
class Percept:
    tick: int
    axis: str          # eixo com o verde (ou que estava, se amarelo)
    phase: str         # GREEN ou YELLOW
    phase_time: int
    queue: dict        # via -> nº de carros na fila (None se o sensor falhou)
    max_wait: dict     # via -> maior espera da fila em ticks (None se falhou)
    emergency: list    # vias com veículo de emergência detectado

    def to_dict(self):
        return asdict(self)


class Sensors:
    def __init__(self):
        self.failed = set()   # vias cujo sensor de fila está quebrado

    def fail(self, direction):
        self.failed.add(direction)

    def repair(self, direction):
        self.failed.discard(direction)

    def read(self, env: Intersection) -> Percept:
        queue, max_wait = {}, {}
        for d in DIRECTIONS:
            if d in self.failed:
                queue[d] = None
                max_wait[d] = None
            else:
                queue[d] = len(env.queues[d])
                max_wait[d] = max((c.waited for c in env.queues[d]), default=0)
        emergency = [d for d in DIRECTIONS if any(c.emergency for c in env.queues[d])]
        s = env.signal
        return Percept(env.tick, s.axis, s.phase, s.phase_time, queue, max_wait, emergency)
