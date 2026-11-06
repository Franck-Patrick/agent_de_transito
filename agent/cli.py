"""Modo somente terminal: roda a simulação e imprime as decisões do agente.

Exemplos:
    python -m agent.cli
    python -m agent.cli -v --ticks 60
    python -m agent.cli --emergency-at 40:E --fail-sensor-at 70:N --repair-sensor-at 110:N
"""
import argparse
import time

from .actuators import SWITCH
from .environment import DIRECTIONS
from .simulation import Simulation

PHASE_PT = {"GREEN": "VERDE", "YELLOW": "AMARELO"}


def parse_event(text):
    """'40:N' -> (40, 'N')"""
    tick, direction = text.split(":")
    direction = direction.upper()
    if direction not in DIRECTIONS:
        raise argparse.ArgumentTypeError(f"via inválida: {direction}")
    return int(tick), direction


def format_line(snap):
    p, d = snap["percept"], snap["decision"]
    queues = " ".join(f"{k}:{'?' if v is None else v}" for k, v in p["queue"].items())
    return (f"t={p['tick']:03d} {p['axis']} {PHASE_PT[p['phase']]:<7} {p['phase_time']:02d} | "
            f"{queues} | {d['action']:<6} [{d['rule']}] {d['reason']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Agente de controle de trânsito (terminal)")
    ap.add_argument("--ticks", type=int, default=120)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--delay", type=float, default=0.0, help="segundos entre ticks")
    ap.add_argument("-v", "--verbose", action="store_true", help="imprime todos os ticks")
    ap.add_argument("--emergency-at", type=parse_event, action="append", default=[], metavar="T:VIA")
    ap.add_argument("--fail-sensor-at", type=parse_event, action="append", default=[], metavar="T:VIA")
    ap.add_argument("--repair-sensor-at", type=parse_event, action="append", default=[], metavar="T:VIA")
    ap.add_argument("--surge-at", type=parse_event, action="append", default=[], metavar="T:VIA")
    args = ap.parse_args(argv)

    schedule = (
        [(t, lambda sim, d=d: sim.inject_emergency(d)) for t, d in args.emergency_at]
        + [(t, lambda sim, d=d: sim.fail_sensor(d)) for t, d in args.fail_sensor_at]
        + [(t, lambda sim, d=d: sim.repair_sensor(d)) for t, d in args.repair_sensor_at]
        + [(t, lambda sim, d=d: sim.set_surge(d, True)) for t, d in args.surge_at]
    )

    sim = Simulation(seed=args.seed)
    print("Legenda: t=tick eixo fase tempo_na_fase | filas por via (? = sensor falhou) | decisão [regra] motivo")
    if not args.verbose:
        print("(mostrando só trocas e eventos; use -v para ver todos os ticks)")
    print()

    for _ in range(args.ticks):
        for t, action in schedule:
            if t == sim.env.tick:
                action(sim)
        snap = sim.step()
        for ev in snap["events"]:
            print(f">> EVENTO: {ev}")
        if args.verbose or snap["decision"]["action"] == SWITCH or snap["events"]:
            print(format_line(snap))
        if args.delay:
            time.sleep(args.delay)

    print("\nDesempenho (P de PEAS):")
    for k, v in sim.performance.metrics().items():
        print(f"  {k:<20} {v}")


if __name__ == "__main__":
    main()
