"""O agente: recebe uma percepção e devolve uma decisão explicada.

Tipo (Russell & Norvig): agente baseado em modelo com função de utilidade simples.
  - baseado em modelo: guarda estado interno (há quanto tempo o verde atual está aberto)
  - utilidade: compara a "pressão" de cada eixo para escolher quem deve passar

As regras são avaliadas em ordem de prioridade. A primeira que casar decide.
Cada decisão carrega o nome da regra e o motivo em texto, para a explicação.
"""
from dataclasses import dataclass, field, asdict

from .actuators import KEEP, SWITCH
from .environment import AXIS_OF, OTHER_AXIS
from .sensors import Percept

MIN_GREEN = 6          # verde mínimo (evita fica-troca-fica-troca)
MAX_GREEN = 30         # verde máximo (evita fome do outro eixo)
FIXED_CYCLE = 15       # tempo do verde no modo reserva (sensor falhou)
WAIT_WEIGHT = 0.2      # quanto a espera pesa na pressão, comparada a 1 carro na fila
SWITCH_MARGIN = 1.5    # o vermelho precisa ter 1.5x a pressão do verde para trocar


@dataclass
class Decision:
    action: str
    rule: str
    reason: str
    metrics: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


class TrafficAgent:
    def __init__(self):
        # estado interno (o "modelo" do mundo que o agente mantém)
        self.green_time = 0
        self.last_axis = None

    def decide(self, p: Percept) -> Decision:
        self._update_model(p)
        green, red = p.axis, OTHER_AXIS[p.axis]

        # 1. Amarelo em andamento: a troca já foi pedida, só esperar.
        if p.phase == "YELLOW":
            return Decision(KEEP, "EM_TRANSICAO", "Amarelo em andamento, aguardando a troca.")

        # 2. Veículo de emergência tem prioridade sobre tudo.
        emergency_axes = {AXIS_OF[d] for d in p.emergency}
        if green in emergency_axes:
            return Decision(KEEP, "EMERGENCIA_NO_VERDE",
                            f"Emergência no eixo {green}, que já está verde. Manter até passar.")
        if red in emergency_axes:
            return Decision(SWITCH, "EMERGENCIA_NO_VERMELHO",
                            f"Emergência detectada em {','.join(p.emergency)} (eixo {red}, vermelho). "
                            f"Trocar já, ignorando verde mínimo.")

        # 3. Sensor de fila falhou: não dá para calcular pressão, usar tempo fixo.
        failed = [d for d, v in p.queue.items() if v is None]
        if failed:
            if self.green_time >= FIXED_CYCLE:
                return Decision(SWITCH, "MODO_RESERVA",
                                f"Sensor falhou em {','.join(failed)}. Tempo fixo: verde há "
                                f"{self.green_time}s (limite {FIXED_CYCLE}s).")
            return Decision(KEEP, "MODO_RESERVA",
                            f"Sensor falhou em {','.join(failed)}. Tempo fixo: verde há "
                            f"{self.green_time}s de {FIXED_CYCLE}s.")

        # A partir daqui os sensores estão ok: calcular as métricas.
        q_green, q_red = self._queue(p, green), self._queue(p, red)
        pr_green, pr_red = self._pressure(p, green), self._pressure(p, red)
        metrics = {"green_axis": green, "red_axis": red,
                   "green_queue": q_green, "red_queue": q_red,
                   "green_pressure": round(pr_green, 1), "red_pressure": round(pr_red, 1),
                   "green_time": self.green_time}

        # 4. Verde mínimo ainda não cumprido.
        if self.green_time < MIN_GREEN:
            return Decision(KEEP, "VERDE_MINIMO",
                            f"Verde há {self.green_time}s, mínimo é {MIN_GREEN}s.", metrics)

        # 5. Verde máximo estourado e há gente esperando no vermelho.
        if self.green_time >= MAX_GREEN and q_red > 0:
            return Decision(SWITCH, "VERDE_MAXIMO",
                            f"Verde há {self.green_time}s (máximo {MAX_GREEN}s) e o eixo {red} "
                            f"tem {q_red} carros esperando.", metrics)

        # 6. Ninguém usando o verde e alguém esperando no vermelho.
        if q_green == 0 and q_red > 0:
            return Decision(SWITCH, "VIA_VAZIA",
                            f"Eixo {green} vazio e eixo {red} com {q_red} carros esperando.", metrics)

        # 7. Utilidade: o vermelho está bem mais pressionado que o verde.
        if pr_red > pr_green * SWITCH_MARGIN:
            return Decision(SWITCH, "PRESSAO",
                            f"Pressão do vermelho {red} ({pr_red:.1f}) passou {SWITCH_MARGIN}x a do "
                            f"verde {green} ({pr_green:.1f}).", metrics)

        # 8. Padrão: nada justifica trocar.
        return Decision(KEEP, "MANTER_VERDE",
                        f"Pressão do verde {green} ({pr_green:.1f}) ainda compensa contra o "
                        f"vermelho {red} ({pr_red:.1f}).", metrics)

    # --- auxiliares ---

    def _update_model(self, p: Percept):
        if p.axis != self.last_axis:
            self.green_time = 0
            self.last_axis = p.axis
        if p.phase == "GREEN":
            self.green_time += 1

    @staticmethod
    def _dirs(axis):
        return [d for d, a in AXIS_OF.items() if a == axis]

    def _queue(self, p: Percept, axis):
        return sum(p.queue[d] for d in self._dirs(axis))

    def _pressure(self, p: Percept, axis):
        """Pressão = carros na fila + peso * maior espera, somado nas vias do eixo."""
        return sum(p.queue[d] + WAIT_WEIGHT * p.max_wait[d] for d in self._dirs(axis))
