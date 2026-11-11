from ..core import Calculation, V

CALCS = [
    Calculation(
        id="robotics.service.differential_drive", name="Differential-drive robot kinematics and runtime",
        disciplines=["robotics", "mechanical"], subdisciplines=["Service Robotics", "Autonomous Systems"],
        description="Forward and angular velocity of a two-wheel robot from wheel speeds, and the battery runtime and range at that operating point.",
        variables=[V("r", "Wheel radius", "mm"), V("Lb", "Wheel separation (track)", "mm", latex=r"b"), V("wl", "Left wheel speed", "rpm", latex=r"\omega_L"), V("wr", "Right wheel speed", "rpm", latex=r"\omega_R"), V("Eb", "Battery energy", "Wh"), V("Pa", "Average electrical power", "W"),
                   V("v", "Forward speed", "m/s"), V("om", "Yaw rate", "deg/s", latex=r"\omega", signed=True), V("tr", "Runtime", "h"), V("rg", "Range", "km")],
        equations=[("Forward speed", "v = r*(wr + wl)/2"), ("Yaw rate", "om = r*(wr - wl)/Lb"), ("Runtime", "tr = Eb/Pa"), ("Range", "rg = v*tr")], outputs=["v", "om", "tr", "rg"], tags=["mobile robot", "vacuum", "agv", "odometry", "kinematics", "battery"],
        assumptions=["No wheel slip, constant power draw"], references=["Siegwart, Nourbakhsh & Scaramuzza, Introduction to Autonomous Mobile Robots, Ch. 3"], example={"r": "35 mm", "Lb": "230 mm", "wl": "120 rpm", "wr": "150 rpm", "Eb": "60 Wh", "Pa": "25 W"}),
    Calculation(
        id="robotics.autonomy.stopping_distance_perception", name="Autonomous vehicle stopping distance and required perception range",
        disciplines=["robotics", "civil", "smartcities"], subdisciplines=["Autonomous Systems", "Connected Vehicles"],
        description="Distance covered during sensing–compute–actuation latency plus braking, and the sensor range needed with a safety margin.",
        variables=[V("v", "Speed", "km/h"), V("tl", "End-to-end latency (perception + planning + actuation)", "ms", latex=r"t_L"), V("a", "Maximum deceleration", "m/s^2"), V("mg", "Safety margin", "m"), V("dl", "Distance during latency", "m", latex=r"d_L"), V("db", "Braking distance", "m", latex=r"d_b"),
                   V("dr", "Required perception range", "m", latex=r"d_{req}")],
        equations=[("Latency distance", "dl = v*tl"), ("Braking distance", "db = v^2/(2*a)"), ("Required range", "dr = dl + db + mg")], outputs=["dl", "db", "dr"], tags=["adas", "lidar", "braking", "sensor range", "latency", "self-driving"], assumptions=["Straight-line stop on a dry surface, constant deceleration"], references=["ISO 22737; Waymo Safety Methodology"],
        example={"v": "90 km/h", "tl": "250 ms", "a": "6 m/s^2", "mg": "10 m"}),
    Calculation(
        id="robotics.swarm.area_coverage", name="Swarm area coverage: robots needed and sweep time",
        disciplines=["robotics", "environmental"], subdisciplines=["Swarm Robotics", "Autonomous Systems"],
        description="Minimum number of robots to cover an area with a given sensing radius and overlap efficiency, and the time for a team to sweep it by lawn-mower paths.",
        variables=[V("A", "Area to cover", "ha"), V("rs", "Sensing / coverage radius", "m", latex=r"r_s"), V("ef", "Packing efficiency", "%", latex=r"\eta_c", min=10, max=100), V("v", "Robot speed", "m/s"), V("N", "Number of robots", "1"), V("Nmin", "Robots for static coverage", "1", latex=r"N_{min}"), V("ts", "Sweep time", "min", latex=r"t_s")],
        equations=[("Static coverage", "Nmin = A/(ef*pi*rs^2)"), ("Sweep time", "ts = A/(N*2*rs*v)")], outputs=["Nmin", "ts"], tags=["multi-robot", "coverage", "search and rescue", "precision agriculture", "uav swarm", "sweep"], assumptions=["Disc footprint (static) or strip of width 2r (sweeping); no turning losses"],
        references=["Choset (2001), Coverage for Robotics, Robotica 19"], example={"A": "25 ha", "rs": "30 m", "ef": "78 %", "v": "5 m/s", "N": "6"}),
    Calculation(
        id="robotics.hri.speed_separation_pfl", name="Human–robot collaboration: separation distance and contact speed limit",
        disciplines=["robotics", "industrial"], subdisciplines=["Human-Robot Interaction", "Industrial Robotics", "Human Factors Engineering"],
        description="Protective separation distance in speed-and-separation monitoring and the maximum robot speed for a permitted transient contact force (ISO/TS 15066 style).",
        variables=[V("vh", "Human approach speed", "mm/s", latex=r"v_h", default=1600), V("vr", "Robot speed toward human", "mm/s", latex=r"v_r"), V("Tr", "Reaction time of system", "ms", latex=r"T_r"), V("Ts", "Robot stopping time", "ms", latex=r"T_s"), V("Ci", "Intrusion distance", "mm", latex=r"C"),
                   V("Zd", "Human position uncertainty", "mm", latex=r"Z_d"), V("Zr", "Robot position uncertainty", "mm", latex=r"Z_r"), V("Sp", "Protective separation distance", "mm", latex=r"S_p"), V("Fmax", "Permitted contact force", "N", latex=r"F_{max}"), V("kb", "Body-region effective stiffness", "N/mm", latex=r"k"),
                   V("mu", "Two-body reduced mass", "kg", latex=r"\mu"), V("vlim", "Maximum contact speed", "mm/s", latex=r"v_{lim}")],
        equations=[("Separation distance", "Sp = vh*(Tr + Ts) + vr*Tr + Ci + Zd + Zr"), ("Contact speed limit", "vlim = Fmax/sqrt(kb*mu)")], outputs=["Sp", "vlim"], tags=["cobot", "iso 10218", "iso ts 15066", "safety", "speed and separation", "power and force limiting"],
        assumptions=["Simplified relations; the standard's body-region tables and risk assessment govern real installations"], references=["ISO 10218-2; ISO/TS 15066:2016"], example={"vh": "1600 mm/s", "vr": "500 mm/s", "Tr": "100 ms", "Ts": "250 ms", "Ci": "200 mm", "Zd": "100 mm", "Zr": "50 mm", "Fmax": "140 N", "kb": "75 N/mm", "mu": "5 kg"}),
    Calculation(
        id="robotics.industrial.pick_place_cycle", name="Pick-and-place cycle time and throughput",
        disciplines=["robotics", "industrial"], subdisciplines=["Industrial Robotics", "Manufacturing Engineering"],
        description="Trapezoidal-profile move time, full cycle time and picks per minute for a pick-and-place robot.",
        variables=[V("d", "Move distance (each way)", "mm"), V("vm", "Peak speed", "mm/s", latex=r"v_{max}"), V("am", "Acceleration", "m/s^2", latex=r"a"), V("tp", "Pick (grip) dwell", "ms", latex=r"t_{pick}"), V("tq", "Place (release) dwell", "ms", latex=r"t_{place}"),
                   V("tm", "Move time (one way)", "ms", latex=r"t_m"), V("tc", "Cycle time", "ms", latex=r"t_c"), V("rate", "Picks per minute", "1/min")],
        equations=[("Move time", "tm = d/vm + vm/am"), ("Cycle time", "tc = 2*tm + tp + tq"), ("Throughput", "rate = 1/tc")], outputs=["tm", "tc", "rate"], tags=["delta robot", "scara", "throughput", "packaging", "cycle time", "pick and place"], validity=[("d > vm^2/am", "move too short to reach peak speed: the trapezoid becomes a triangle (formula over-predicts time)")],
        assumptions=["Symmetric accel/decel, equal out and return moves"], references=["Craig, Introduction to Robotics, Ch. 7"], example={"d": "300 mm", "vm": "1500 mm/s", "am": "15 m/s^2", "tp": "80 ms", "tq": "60 ms"}),
]
