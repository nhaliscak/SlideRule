from ..core import C, Calculation, V
from ._common import mu0

CALCS = [
    Calculation(
        id="electromechanical.electromagnetics.electromagnet_force", name="C-core electromagnet gap flux and pull force",
        disciplines=["electromechanical", "electrical"], subdisciplines=["Electromechanics", "Mechatronics"],
        description="Air-gap flux density and total pull force of a C-core electromagnet with two equal gaps and negligible iron reluctance.",
        variables=[V("N", "Coil turns", "1"), V("I", "Coil current", "A"), V("g", "Length of each air gap", "mm"), V("Ag", "Pole face area", "cm^2", latex=r"A_g"), mu0(),
                   V("B", "Gap flux density", "T"), V("F", "Total pull force", "N")],
        equations=[("Flux density", "B = mu0*N*I/(2*g)"), ("Pull force", "F = B^2*Ag/mu0")], outputs=["B", "F"], tags=["electromagnet", "solenoid", "magnetic circuit", "actuator", "relay", "pull force"],

        assumptions=["Infinite iron permeability, no fringing or leakage; B below saturation (~1.5 T)"], references=["Fitzgerald, Kingsley & Umans, Electric Machinery, Ch. 3"],
        example={"N": "500", "I": "2 A", "g": "2 mm", "Ag": "4 cm^2"}),
    Calculation(
        id="electromechanical.actuators.voice_coil_force", name="Voice-coil (Lorentz) actuator",
        disciplines=["electromechanical", "electrical"], subdisciplines=["Electromechanics", "Mechatronics", "Biomechatronics"],
        description="Force, force constant and resistive power of a voice-coil actuator, F = B·N·L·I.",
        variables=[V("B", "Magnetic flux density in the gap", "T"), V("Lw", "Wire length per turn in field", "mm", latex=r"\ell"), V("N", "Turns", "1"), V("I", "Current", "A"), V("R", "Coil resistance", "ohm"),
                   V("Kf", "Force constant", "N/A", latex=r"K_f"), V("F", "Force", "N"), V("P", "Resistive power", "W")],
        equations=[("Force constant", "Kf = B*Lw*N"), ("Force", "F = Kf*I"), ("Power", "P = I^2*R")], outputs=["Kf", "F", "P"], tags=["voice coil", "lorentz", "linear actuator", "speaker", "haptic"],
        assumptions=["Uniform field over the active winding"], references=["Kenjo & Nagamori, Permanent-Magnet and Brushless DC Motors"], example={"B": "0.8 T", "Lw": "60 mm", "N": "100", "I": "1.5 A", "R": "4 ohm"}),
    Calculation(
        id="electromechanical.mechatronics.lead_screw_drive", name="Lead-screw drive: speed and thrust",
        disciplines=["electromechanical", "mechanical"], subdisciplines=["Mechatronics", "Electromechanics", "Industrial Robotics"],
        description="Linear speed and thrust force of a lead-screw (or ball-screw) actuator from motor speed, torque, lead and efficiency.",
        variables=[V("lead", "Screw lead (travel per revolution)", "mm"), V("n", "Motor speed", "rpm"), V("T", "Motor torque", "N*m"), V("eta", "Screw efficiency", "%", latex=r"\eta", min=1, max=100),
                   V("v", "Linear speed", "mm/s"), V("F", "Thrust force", "N")],
        equations=[("Linear speed", "v = lead*n/(2*pi)"), ("Thrust", "F = 2*pi*eta*T/lead")], outputs=["v", "F"], tags=["lead screw", "ball screw", "linear motion", "actuator", "cnc"],
        assumptions=["Rigid, no backlash; efficiency from friction (≈ 90 % ball screw, 30–50 % lead screw)"], references=["Budynas & Nisbett, Shigley's Mechanical Engineering Design, Ch. 8"], example={"lead": "5 mm", "n": "1500 rpm", "T": "0.5 N*m", "eta": "90 %"}),
    Calculation(
        id="electromechanical.mechatronics.stepper_resolution", name="Stepper motor resolution and speed",
        disciplines=["electromechanical", "mechanical"], subdisciplines=["Mechatronics", "Control Engineering"],
        description="Angular and linear resolution of a micro-stepped stepper axis, and the speed for a given step pulse rate.",
        variables=[C("rev1", "One revolution", 1, "rev", latex=r"1\,\mathrm{rev}"), V("spr", "Full steps per revolution", "1", default=200), V("ms", "Microsteps per full step", "1", default=16), V("lead", "Lead (travel per revolution)", "mm"), V("fst", "Step pulse frequency", "kHz", latex=r"f_{step}"),
                   V("ares", "Angular resolution", "deg"), V("lres", "Linear resolution", "um"), V("v", "Linear speed", "mm/s"), V("n", "Shaft speed", "rpm")],
        equations=[("Angular resolution", "ares = rev1/(spr*ms)"), ("Linear resolution", "lres = lead/(spr*ms)"), ("Linear speed", "v = lead*fst/(spr*ms)"), ("Shaft speed", "n = 2*pi*fst/(spr*ms)")],
        outputs=["ares", "lres", "v", "n"], tags=["stepper", "microstepping", "resolution", "3d printer", "positioning"], assumptions=["No missed steps; speed limited by torque–speed curve"],
        references=["Acarnley, Stepping Motors: A Guide to Theory and Practice"], example={"spr": "200", "ms": "16", "lead": "8 mm", "fst": "20 kHz"}),
    Calculation(
        id="electromechanical.mechatronics.servo_torque_sizing", name="Servo axis torque sizing with trapezoidal move",
        disciplines=["electromechanical", "mechanical", "robotics"], subdisciplines=["Mechatronics", "Control Engineering", "Industrial Robotics"],
        description="Peak motor torque from reflected inertia and load torque, plus the time of a trapezoidal rotary move.",
        variables=[V("J", "Total reflected inertia", "kg*m^2"), V("wmax", "Maximum speed", "rpm", latex=r"\omega_{max}"), V("al", "Acceleration", "rad/s^2", latex=r"\alpha"), V("Tl", "Load/friction torque", "N*m", latex=r"T_L"),
                   V("th", "Move angle", "rev", latex=r"\theta"), V("Tp", "Peak torque", "N*m", latex=r"T_{peak}"), V("ta", "Acceleration time", "s", latex=r"t_a"), V("tt", "Total move time", "s", latex=r"t_{tot}"), V("Pp", "Peak mechanical power", "W", latex=r"P_{peak}")],
        equations=[("Peak torque", "Tp = J*al + Tl"), ("Acceleration time", "ta = wmax/al"), ("Move time", "tt = th/wmax + wmax/al"), ("Peak power", "Pp = Tp*wmax")], outputs=["Tp", "ta", "tt", "Pp"],
        tags=["servo", "motion profile", "inertia", "motor selection", "trapezoidal"],
        assumptions=["Move long enough to reach full speed (θ ≥ ω²/α); constant load torque"], references=["Budynas & Nisbett; Kollmorgen Motion Control Handbook"], example={"J": "0.0004 kg*m^2", "wmax": "3000 rpm", "al": "5000 rad/s^2", "Tl": "0.2 N*m", "th": "20 rev"}),
]
