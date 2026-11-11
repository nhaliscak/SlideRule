"""Disciplines and sub-disciplines.

The structure mirrors ``docs/reference/disciplines.txt`` (a test keeps them in sync). A calculation belongs to one or more
*disciplines* (top-level headings) and is tagged with the *sub-disciplines* it serves.
``architectural``, ``physics`` and ``chemistry`` are extra disciplines requested separately from that file.
"""

from __future__ import annotations

# id -> (display name as in the reference file, group, sub-disciplines)
TAXONOMY: dict[str, tuple[str, str, list[str]]] = {
    "aerospace": ("Aerospace Engineering", "core", [
        "Aeronautical Engineering", "Astronautical Engineering", "Propulsion Engineering", "Avionics Engineering",
        "Space Systems Engineering", "Aerodynamics"]),
    "agricultural": ("Agricultural Engineering", "core", [
        "Bioengineering", "Irrigation Engineering", "Farm Machinery Engineering", "Soil and Water Engineering",
        "Agricultural Structures Engineering", "Food Engineering"]),
    "biomedical": ("Biomedical Engineering", "core", [
        "Bioinformatics", "Bioinstrumentation", "Biomaterials", "Biomechanics", "Biomolecular Engineering",
        "Clinical Engineering", "Medical Imaging", "Neural Engineering", "Pharmaceutical Engineering",
        "Regenerative Medicine / Tissue Engineering", "Biomechatronics", "Medical Device Engineering", "Bioprinting"]),
    "chemical": ("Chemical Engineering", "core", [
        "Process Engineering", "Molecular Engineering", "Electrochemical Engineering", "Biochemical Engineering",
        "Petrochemical Engineering", "Pharmaceutical Engineering", "Polymer Engineering",
        "Environmental Chemical Engineering", "Nuclear Engineering", "Corrosion Engineering", "Food Engineering",
        "Textile Engineering", "Refinery Engineering", "Fuel Cell Engineering", "Pulp and Paper Engineering",
        "Powder Technology"]),
    "civil": ("Civil Engineering", "core", [
        "Structural Engineering", "Geotechnical Engineering", "Transportation Engineering", "Environmental Engineering",
        "Water Resources Engineering", "Construction Engineering", "Municipal / Urban Engineering",
        "Architectural Engineering", "Hydraulic Engineering", "Coastal Engineering", "Earthquake Engineering",
        "Pavement Engineering", "Wind Engineering", "Sanitary Engineering", "Railway Engineering",
        "Highway Engineering", "Ocean Engineering", "River Engineering", "Groundwater Engineering"]),
    "computer": ("Computer / Software Engineering", "core", [
        "Software Engineering", "Computer Engineering", "Embedded Systems Engineering", "Network Engineering",
        "Cybersecurity Engineering", "Data Engineering", "AI / Machine Learning Engineering", "Cloud Engineering",
        "IoT Engineering", "Computer-Aided Engineering", "Knowledge Engineering", "Usability Engineering",
        "Teletraffic Engineering"]),
    "electrical": ("Electrical Engineering", "core", [
        "Power Systems Engineering", "Electronics Engineering", "Telecommunications Engineering",
        "Control Systems Engineering", "Signal Processing", "Optoelectronics / Photonics", "RF and Microwave Engineering",
        "Power Electronics", "Instrumentation Engineering", "Broadcast Engineering", "Satellite Communication",
        "Smart Grid Engineering", "Electrical Machines and Drives", "Wireless Communication"]),
    "electromechanical": ("Electromechanical Engineering", "core", [
        "Mechatronics", "Control Engineering", "Instrumentation Engineering", "Electromechanics"]),
    "environmental": ("Environmental Engineering", "core", [
        "Sanitary Engineering", "Ecological Engineering", "Fire Protection Engineering", "Natural Resources Engineering",
        "Water and Wastewater Treatment", "Pollution Control", "Environmental Impact Assessment"]),
    "industrial": ("Industrial Engineering", "core", [
        "Systems Engineering", "Supply Chain Engineering", "Manufacturing Engineering", "Quality Control",
        "Logistics Engineering", "Ergonomics", "Operations Research", "Human Factors Engineering"]),
    "materials": ("Materials Engineering", "core", [
        "Metallurgical Engineering", "Ceramic Engineering", "Polymer Engineering", "Composite Materials Engineering",
        "Nanotechnology", "Corrosion Engineering", "Surface Engineering", "Welding Engineering",
        "Computational Materials Science", "Electronic Materials", "Forensic Materials Engineering", "Tribology"]),
    "mechanical": ("Mechanical Engineering", "core", [
        "Aerospace Engineering", "Automotive Engineering", "Marine / Naval Engineering", "Thermal Engineering",
        "Acoustical Engineering", "Manufacturing Engineering", "Energy Engineering", "Power Plant Engineering",
        "Vehicle Engineering", "Optomechanical Engineering", "Industrial Plant Engineering", "Robotics",
        "Sports Engineering", "Refrigeration Engineering", "Fluid Mechanics"]),
    "mining": ("Mining Engineering", "core", [
        "Mineral Processing", "Geotechnical Mining", "Ventilation Engineering", "Surface Mining", "Underground Mining",
        "Mine Safety Engineering"]),
    "nuclear": ("Nuclear Engineering", "core", [
        "Reactor Engineering", "Radiation Safety", "Nuclear Fuel Engineering", "Nuclear Waste Management",
        "Radiological Engineering"]),
    "petroleum": ("Petroleum Engineering", "core", [
        "Reservoir Engineering", "Drilling Engineering", "Production Engineering", "Petroleum Geology"]),
    "systems": ("Systems Engineering", "core", [
        "Requirements Engineering", "Integration Engineering", "Verification and Validation",
        "Software Systems Engineering"]),
    "architectural": ("Architectural Engineering", "core", ["Architectural Engineering"]),
    # Physics and chemistry as sciences (requested separately from the reference file, like architectural)
    "physics": ("Physics", "core", [
        "Classical Mechanics", "Thermodynamics and Statistical Physics", "Waves and Acoustics", "Optics",
        "Electricity and Magnetism", "Modern Physics", "Gravitation and Astrophysics", "Fluid Mechanics", "Atomic and Molecular Physics", "Solid State Physics", "Nuclear and Particle Physics",
        "Quantum Mechanics", "Statistical Mechanics", "Analytical Mechanics", "Plasma Physics", "Nonlinear Dynamics and Chaos"]),
    "chemistry": ("Chemistry", "core", [
        "General Chemistry", "Physical Chemistry", "Analytical Chemistry", "Atomic Structure and Spectroscopy", "Chemical Thermodynamics", "Chemical Kinetics", "Electrochemistry", "Solid-State and Inorganic Chemistry", "Organic Chemistry",
        "Quantum Chemistry", "Photochemistry", "Polymer Chemistry", "Colloid and Surface Chemistry", "Biochemistry", "Atmospheric Chemistry"]),
    # --- Emerging and interdisciplinary fields
    "quantum": ("Quantum Engineering", "emerging", ["Quantum Computing", "Quantum Sensing", "Quantum Communication / Cryptography"]),
    "aiml": ("Artificial Intelligence and Machine Learning Engineering", "emerging", [
        "Deep Learning Systems", "Natural Language Processing", "Computer Vision", "Reinforcement Learning",
        "Generative AI Systems"]),
    "robotics": ("Robotics and Automation Engineering", "emerging", [
        "Industrial Robotics", "Service Robotics", "Swarm Robotics", "Autonomous Systems", "Human-Robot Interaction"]),
    "cybersecurity": ("Cybersecurity Engineering", "emerging", [
        "Network Security", "Cryptographic Engineering", "Threat Intelligence", "Secure Software Design", "Digital Forensics"]),
    "data": ("Data Science and Big Data Engineering", "emerging", [
        "Data Architecture", "Data Warehousing", "Streaming Data Processing", "Business Intelligence"]),
    "nanotech": ("Nanotechnology Engineering", "emerging", [
        "Nanoelectronics", "Nanomedicine", "Nanomaterials", "Nano-biosensors"]),
    "synbio": ("Synthetic Biology Engineering", "emerging", [
        "Genetic Circuit Design", "Metabolic Engineering", "Biomanufacturing", "CRISPR Engineering"]),
    "climate": ("Climate and Resilience Engineering", "emerging", [
        "Geoengineering", "Carbon Capture and Sequestration", "Climate Adaptation Design", "Resilient Infrastructure"]),
    "smartcities": ("Smart Cities and IoT Engineering", "emerging", [
        "Urban Sensing", "Smart Infrastructure", "Connected Vehicles", "Digital Twin Systems"]),
    "neuro": ("Neuromorphic and Brain-Computer Interface Engineering", "emerging", [
        "Neuromodulation", "Neuroprosthetics", "Brain-Computer Interfaces", "Neuromorphic Computing"]),
    "energy": ("Renewable and Sustainable Energy Engineering", "emerging", [
        "Solar Energy Engineering", "Wind Energy Engineering", "Hydrogen Energy", "Energy Storage / Battery Engineering",
        "Smart Grid and Microgrid Design", "Electric Vehicle Engineering"]),
    "healthinfo": ("Health Informatics and Health Science Engineering", "emerging", [
        "Clinical Data Systems", "Telemedicine Engineering", "Wearable Medical Devices", "AI-Assisted Diagnostics"]),
    "additive": ("Additive Manufacturing Engineering", "emerging", [
        "3D Printing", "Metal Additive Manufacturing", "Bioprinting", "4D Printing"]),
    "space": ("Space Engineering", "emerging", [
        "Satellite Systems", "Space Propulsion", "Planetary Exploration", "Space Debris Management"]),
    "metamaterials": ("Metamaterials and Advanced Materials Engineering", "emerging", [
        "Metamaterials Design", "Smart / Adaptive Materials", "Self-Healing Materials", "Holographic Engineering"]),
    "green": ("Green / Sustainable Engineering", "emerging", [
        "Life Cycle Assessment", "Industrial Ecology", "Circular Economy Design", "Eco-Design"]),
    "softrobotics": ("Wearable and Soft Robotics Engineering", "emerging", [
        "Smart Textiles", "Soft Actuators", "Exoskeletons", "Health Monitoring Wearables"]),
}

# Short display names for UI chips (the long reference names are kept in TAXONOMY).
SHORT_NAMES: dict[str, str] = {
    "computer": "Computer / Software", "electromechanical": "Electromechanical", "aiml": "AI / Machine Learning",
    "robotics": "Robotics & Automation", "data": "Data Science", "nanotech": "Nanotechnology",
    "synbio": "Synthetic Biology", "climate": "Climate & Resilience", "smartcities": "Smart Cities & IoT",
    "neuro": "Neuromorphic & BCI", "energy": "Renewable Energy", "healthinfo": "Health Informatics",
    "additive": "Additive Manufacturing", "space": "Space", "metamaterials": "Advanced Materials",
    "green": "Green / Sustainable", "softrobotics": "Wearable & Soft Robotics", "quantum": "Quantum",
    "cybersecurity": "Cybersecurity",
}


def _short(did: str, full: str) -> str:
    return SHORT_NAMES.get(did) or full.removesuffix(" Engineering")


DISCIPLINES: dict[str, str] = {k: _short(k, v[0]) for k, v in TAXONOMY.items()}
GROUPS: dict[str, str] = {k: v[1] for k, v in TAXONOMY.items()}
SUBDISCIPLINES: dict[str, list[str]] = {}
for _did, (_name, _grp, _subs) in TAXONOMY.items():
    for _s in _subs:
        SUBDISCIPLINES.setdefault(_s, []).append(_did)
