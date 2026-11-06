"""Testes das regras do agente e do ambiente. Rodar: pytest"""
from agent.actuators import KEEP, SWITCH
from agent.agent import FIXED_CYCLE, MAX_GREEN, MIN_GREEN, TrafficAgent
from agent.environment import YELLOW_TICKS, Intersection
from agent.sensors import Percept
from agent.simulation import Simulation


def percept(queue, axis="NS", phase="GREEN", max_wait=None, emergency=()):
    max_wait = max_wait or {d: 0 for d in queue}
    return Percept(0, axis, phase, 0, queue, max_wait, list(emergency))


def agent_with_green_time(t, axis="NS"):
    a = TrafficAgent()
    a.last_axis, a.green_time = axis, t - 1   # decide() soma 1
    return a


# --- regras do agente ---

def test_respeita_verde_minimo():
    a = agent_with_green_time(1)
    d = a.decide(percept({"N": 0, "S": 0, "E": 9, "W": 9}))
    assert (d.action, d.rule) == (KEEP, "VERDE_MINIMO")


def test_troca_quando_verde_vazio():
    a = agent_with_green_time(MIN_GREEN)
    d = a.decide(percept({"N": 0, "S": 0, "E": 2, "W": 0}))
    assert (d.action, d.rule) == (SWITCH, "VIA_VAZIA")


def test_troca_por_pressao():
    a = agent_with_green_time(MIN_GREEN)
    d = a.decide(percept({"N": 1, "S": 1, "E": 5, "W": 4}))
    assert (d.action, d.rule) == (SWITCH, "PRESSAO")


def test_mantem_quando_verde_compensa():
    a = agent_with_green_time(MIN_GREEN)
    d = a.decide(percept({"N": 4, "S": 3, "E": 2, "W": 1}))
    assert (d.action, d.rule) == (KEEP, "MANTER_VERDE")


def test_verde_maximo_evita_fome():
    a = agent_with_green_time(MAX_GREEN)
    d = a.decide(percept({"N": 9, "S": 9, "E": 1, "W": 0}))
    assert (d.action, d.rule) == (SWITCH, "VERDE_MAXIMO")


def test_emergencia_no_vermelho_ignora_verde_minimo():
    a = agent_with_green_time(1)
    d = a.decide(percept({"N": 5, "S": 5, "E": 1, "W": 0}, emergency=["E"]))
    assert (d.action, d.rule) == (SWITCH, "EMERGENCIA_NO_VERMELHO")


def test_emergencia_no_verde_segura_o_sinal():
    a = agent_with_green_time(MAX_GREEN + 5)
    d = a.decide(percept({"N": 1, "S": 0, "E": 9, "W": 9}, emergency=["N"]))
    assert (d.action, d.rule) == (KEEP, "EMERGENCIA_NO_VERDE")


def test_sensor_falho_usa_tempo_fixo():
    q = {"N": None, "S": 3, "E": 0, "W": 0}
    mw = {"N": None, "S": 0, "E": 0, "W": 0}
    assert agent_with_green_time(MIN_GREEN).decide(percept(q, max_wait=mw)).action == KEEP
    d = agent_with_green_time(FIXED_CYCLE).decide(percept(q, max_wait=mw))
    assert (d.action, d.rule) == (SWITCH, "MODO_RESERVA")


def test_amarelo_nao_decide():
    d = TrafficAgent().decide(percept({"N": 0, "S": 0, "E": 9, "W": 9}, phase="YELLOW"))
    assert (d.action, d.rule) == (KEEP, "EM_TRANSICAO")


# --- ambiente ---

def test_amarelo_dura_e_depois_troca_eixo():
    env = Intersection(seed=1)
    env.arrival_prob = {d: 0 for d in env.arrival_prob}
    env.start_yellow()
    for _ in range(YELLOW_TICKS):
        env.step()
    assert (env.signal.axis, env.signal.phase) == ("EW", "GREEN")


def test_ninguem_passa_no_vermelho_nem_no_amarelo():
    env = Intersection(seed=1)
    env.arrival_prob = {d: 0 for d in env.arrival_prob}
    env.add_car("E")
    env.add_car("N")
    env.start_yellow()
    env.step()
    assert env.departed == []
    assert len(env.queues["E"]) == 1


# --- integração ---

def test_simulacao_deterministica_com_seed():
    a, b = Simulation(seed=3), Simulation(seed=3)
    for _ in range(80):
        sa, sb = a.step(), b.step()
    assert sa == sb


def test_ambulancia_passa_rapido():
    sim = Simulation(seed=7)
    for _ in range(20):
        sim.step()
    red = "E" if sim.env.signal.axis == "NS" else "N"
    sim.inject_emergency(red)
    for _ in range(10):
        sim.step()
    assert sim.performance.emergency_passed == 1
    assert sim.performance.max_emergency_wait <= 5
