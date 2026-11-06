"""A de PEAS: atuadores.

O agente só tem um jeito de agir sobre o mundo: pedir ao semáforo para trocar
ou para manter. O atuador traduz a decisão em ação no ambiente.
O amarelo é obrigatório (segurança): o agente não consegue pular direto de verde para verde.
"""
from .environment import Intersection

KEEP = "KEEP"
SWITCH = "SWITCH"


class SignalActuator:
    def __init__(self, env: Intersection):
        self.env = env

    def execute(self, action):
        if action == SWITCH:
            self.env.start_yellow()
