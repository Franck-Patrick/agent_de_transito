"""Junta P, E, A, S e o agente. Cada step() é um ciclo percepção -> decisão -> ação."""
from .actuators import SWITCH, SignalActuator
from .agent import TrafficAgent
from .environment import DEFAULT_ARRIVAL_PROB, DIRECTIONS, SURGE_ARRIVAL_PROB, Intersection
from .performance import Performance
from .sensors import Sensors


class Simulation:
    def __init__(self, seed=None):
        self.env = Intersection(seed)
        self.sensors = Sensors()
        self.actuator = SignalActuator(self.env)
        self.agent = TrafficAgent()
        self.performance = Performance()
        self._events = []

    def step(self):
        percept = self.sensors.read(self.env)
        decision = self.agent.decide(percept)
        self.actuator.execute(decision.action)
        if decision.action == SWITCH:
            self.performance.record_switch()
        self.env.step()
        self.performance.update(self.env)

        events, self._events = self._events, []
        return self.snapshot(percept, decision, events)

    def snapshot(self, percept, decision, events):
        s = self.env.signal
        return {
            "tick": self.env.tick,
            "signal": {"axis": s.axis, "phase": s.phase, "phase_time": s.phase_time},
            "queues": {d: [{"id": c.id, "emergency": c.emergency, "waited": c.waited}
                           for c in self.env.queues[d]] for d in DIRECTIONS},
            "percept": percept.to_dict(),
            "decision": decision.to_dict(),
            "performance": self.performance.metrics(),
            "sensors_failed": sorted(self.sensors.failed),
            "surge": sorted(d for d in DIRECTIONS
                            if self.env.arrival_prob[d] > DEFAULT_ARRIVAL_PROB),
            "events": events,
        }

    # --- cartas surpresa ---

    def inject_emergency(self, direction):
        self.env.add_car(direction, emergency=True)
        self._events.append(f"Ambulância chegou na via {direction}")

    def fail_sensor(self, direction):
        self.sensors.fail(direction)
        self._events.append(f"Sensor da via {direction} falhou")

    def repair_sensor(self, direction):
        self.sensors.repair(direction)
        self._events.append(f"Sensor da via {direction} reparado")

    def set_surge(self, direction, on):
        self.env.arrival_prob[direction] = SURGE_ARRIVAL_PROB if on else DEFAULT_ARRIVAL_PROB
        self._events.append(f"Pico de tráfego {'iniciado' if on else 'encerrado'} na via {direction}")
