import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath("d:/ERM"))
import psycopg2
from psycopg2.extras import RealDictCursor
from ERM_Copilot.services.db_service import ERMDatabaseService, DB_SCHEMA

def reset_and_seed_data():
    db = ERMDatabaseService()
    conn = db._get_connection(readonly=False)
    if not conn:
        print("Failed to connect to database.")
        return False
    
    cur = conn.cursor(cursor_factory=RealDictCursor)
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    try:
        print("1. Truncating risk tables...")
        cur.execute(f"TRUNCATE TABLE {DB_SCHEMA}.risk_action_followup RESTART IDENTITY CASCADE;")
        cur.execute(f"TRUNCATE TABLE {DB_SCHEMA}.risk_treatment_hist RESTART IDENTITY CASCADE;")
        cur.execute(f"TRUNCATE TABLE {DB_SCHEMA}.risk_treatment RESTART IDENTITY CASCADE;")
        cur.execute(f"TRUNCATE TABLE {DB_SCHEMA}.risk_description_hist RESTART IDENTITY CASCADE;")
        cur.execute(f"TRUNCATE TABLE {DB_SCHEMA}.risk_description RESTART IDENTITY CASCADE;")
        cur.execute(f"TRUNCATE TABLE {DB_SCHEMA}.risk_register_hist RESTART IDENTITY CASCADE;")
        cur.execute(f"TRUNCATE TABLE {DB_SCHEMA}.risk_register RESTART IDENTITY CASCADE;")
        cur.execute(f"TRUNCATE TABLE {DB_SCHEMA}.mst_email_job RESTART IDENTITY CASCADE;")

        # Update last_risk_number in mst_department
        cur.execute(f"UPDATE {DB_SCHEMA}.mst_department SET last_risk_number = 0;")

        # Seed data definition for 6 departments (2-3 risks each)
        # Dept 1: Refining Operations (REF) - RO: Karan (5), AO: Sunil (6), FH: Vikram (4)
        # Dept 2: Gas Processing Facilities (GAS) - RO: Rohan (8), AO: Deepak (9), FH: Ananya (7)
        # Dept 3: Health, Safety & Environment (HSSE) - RO: Priyanka (11), AO: Manoj (12), FH: Suresh (10)
        # Dept 4: Maintenance & Engineering (MAINT) - RO: Gaurav (14), AO: Sanjay (15), FH: Arun (13)
        # Dept 5: Finance & Commercial (FIN) - RO: Nikhil (17), AO: Ritu (18), FH: Sneha (16)
        # Dept 6: Information Technology & SCADA (IT) - RO: Alok (20), AO: Kavita (21), FH: Vivek (19)

        risks_data = [
            # --- Department 1: Refining Operations (REF) ---
            {
                "dept_id": 1,
                "dept_code": "REF",
                "risk_id": "RSK-REF-001",
                "risk_name": "Crude Distillation Unit (CDU) Column Top Tray Corrosion & Thinning",
                "description": "High sulfur crude blends accelerating internal acid/chloride corrosion on top fractionation trays, leading to unplanned shutdown or vapor leak.",
                "mitigation": "Install continuous ultrasonic thickness monitoring, inject neutralizing amine inhibitors, and perform monthly overhead stream analysis.",
                "owner_id": 5,
                "action_owner_id": 6,
                "risk_status": 3,  # Function Head Approved -> Pending RM Approval
                "fh_status": 1,
                "fh_remark": "Corrosion mitigation protocol reviewed and endorsed for execution.",
                "fh_by": 4,
                "rm_status": None,
                "rm_remark": None,
                "rm_by": None,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Install automated chemical injection skids and conduct online corrosion mapping across CDU column 101.",
                "target_date": (now + timedelta(days=45)).strftime("%Y-%m-%d"),
                "progress": 30,
                "inherent_l": 4, "inherent_i": 5, "curr_l": 2, "curr_i": 3
            },
            {
                "dept_id": 1,
                "dept_code": "REF",
                "risk_id": "RSK-REF-002",
                "risk_name": "Fluid Catalytic Cracking (FCC) Main Air Blower Mechanical Seal Failure",
                "description": "High thermal cyclic fatigue and vibration on main air blower rotor seals risking catalyst circulation trip and emergency flaring.",
                "mitigation": "Deploy 24x7 wireless vibration sensors, dry gas seal buffer system upgrade, and quarterly lube oil filtration.",
                "owner_id": 5,
                "action_owner_id": 6,
                "risk_status": 2,  # Submitted -> Pending FH Approval
                "fh_status": 0,
                "fh_remark": None,
                "fh_by": None,
                "rm_status": None,
                "rm_remark": None,
                "rm_by": None,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Replace dry gas seal cartridge with tungsten carbide faces during upcoming mini-turnaround window.",
                "target_date": (now + timedelta(days=60)).strftime("%Y-%m-%d"),
                "progress": 15,
                "inherent_l": 4, "inherent_i": 4, "curr_l": 2, "curr_i": 3
            },
            {
                "dept_id": 1,
                "dept_code": "REF",
                "risk_id": "RSK-REF-003",
                "risk_name": "Hydrocracker High Pressure Recycle Gas Compressor Valve Leakage",
                "description": "Reciprocating compressor suction valve degradation under 150 bar hydrogen service causing temperature surge and throughput curtailment.",
                "mitigation": "Switch to PEEK valve plates, implement real-time PV curve diagnostic monitoring, and keep certified spare assemblies on skid.",
                "owner_id": 5,
                "action_owner_id": 6,
                "risk_status": 4,  # Risk Manager Approved -> Pending RH Approval
                "fh_status": 1,
                "fh_remark": "Reviewed and agreed on hydrogen safety measures.",
                "fh_by": 4,
                "rm_status": 1,
                "rm_remark": "Adequate technical controls and spare parts management verified.",
                "rm_by": 3,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Procure OEM PEEK valve retrofit kit and complete cold-end overhaul.",
                "target_date": (now + timedelta(days=30)).strftime("%Y-%m-%d"),
                "progress": 50,
                "inherent_l": 5, "inherent_i": 5, "curr_l": 2, "curr_i": 2
            },

            # --- Department 2: Gas Processing Facilities (GAS) ---
            {
                "dept_id": 2,
                "dept_code": "GAS",
                "risk_id": "RSK-GAS-001",
                "risk_name": "Gas Sweetening Amine Unit Contamination & Foaming Overcarry",
                "description": "Heavy hydrocarbon entrainment in MDEA absorber column causing severe foaming, reduced acid gas absorption, and off-spec sales gas.",
                "mitigation": "Install coalescing inlet filter-separators, maintain continuous carbon bed filtration, and auto-dose anti-foam agent.",
                "owner_id": 8,
                "action_owner_id": 9,
                "risk_status": 3,  # Function Head Approved -> Pending RM Approval
                "fh_status": 1,
                "fh_remark": "Endorsed. Ensure coalescer elements meet micron specifications.",
                "fh_by": 7,
                "rm_status": None,
                "rm_remark": None,
                "rm_by": None,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Retrofit feed gas coalescer vessel with high-efficiency micro-fiber cartridges.",
                "target_date": (now + timedelta(days=40)).strftime("%Y-%m-%d"),
                "progress": 25,
                "inherent_l": 4, "inherent_i": 4, "curr_l": 2, "curr_i": 2
            },
            {
                "dept_id": 2,
                "dept_code": "GAS",
                "risk_id": "RSK-GAS-002",
                "risk_name": "TEG Dehydration Unit Reboiler Thermal Degradation & Emissions",
                "description": "Excessive skin temperature in glycol reboiler firetube causing thermal decomposition, triethylene glycol loss, and BTEX emissions.",
                "mitigation": "Calibrate burner air-fuel ratio controllers, install flue gas oxygen analyzer, and implement automated temperature trip logic.",
                "owner_id": 8,
                "action_owner_id": 9,
                "risk_status": 2,  # Submitted -> Pending FH Approval
                "fh_status": 0,
                "fh_remark": None,
                "fh_by": None,
                "rm_status": None,
                "rm_remark": None,
                "rm_by": None,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Upgrade reboiler burner management system (BMS) with SIL-2 compliant flame scanners.",
                "target_date": (now + timedelta(days=75)).strftime("%Y-%m-%d"),
                "progress": 10,
                "inherent_l": 3, "inherent_i": 4, "curr_l": 2, "curr_i": 2
            },
            {
                "dept_id": 2,
                "dept_code": "GAS",
                "risk_id": "RSK-GAS-003",
                "risk_name": "Cryogenic NGL Fractionation Cold Box Heat Exchanger Hydrate Blockage",
                "description": "Trace moisture breakthrough into cryogenic expander section causing methane/ethane hydrate formation and differential pressure spike.",
                "mitigation": "Install dual online dewpoint analyzers, automated methanol injection skids, and dual molecular sieve bed regeneration.",
                "owner_id": 8,
                "action_owner_id": 9,
                "risk_status": 4,  # Risk Manager Approved -> Pending RH Approval
                "fh_status": 1,
                "fh_remark": "Approved for enterprise risk register.",
                "fh_by": 7,
                "rm_status": 1,
                "rm_remark": "Risk controls and emergency depressurization procedures verified.",
                "rm_by": 3,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Replace molecular sieve desiccant 4A with high-capacity low-dust adsorbent.",
                "target_date": (now + timedelta(days=35)).strftime("%Y-%m-%d"),
                "progress": 60,
                "inherent_l": 5, "inherent_i": 5, "curr_l": 2, "curr_i": 2
            },

            # --- Department 3: Health, Safety & Environment (HSSE) ---
            {
                "dept_id": 3,
                "dept_code": "HSSE",
                "risk_id": "RSK-HSSE-001",
                "risk_name": "H2S Sour Gas Release Risk at Sulfur Recovery Unit (SRU) Tail Gas",
                "description": "Potential fugitive hydrogen sulfide release from SRU incinerator bypass valve during sudden plant upset, exceeding permissible exposure limits.",
                "mitigation": "Deploy fixed wireless open-path optical gas detectors, personal multi-gas monitors, automated perimeter water curtains, and quarterly emergency drills.",
                "owner_id": 11,
                "action_owner_id": 12,
                "risk_status": 3,  # Function Head Approved -> Pending RM Approval
                "fh_status": 1,
                "fh_remark": "HSE life-safety review completed. Water curtain coverage verified.",
                "fh_by": 10,
                "rm_status": None,
                "rm_remark": None,
                "rm_by": None,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Install 6 additional laser open-path H2S detectors along the SRU battery limit fence line.",
                "target_date": (now + timedelta(days=30)).strftime("%Y-%m-%d"),
                "progress": 40,
                "inherent_l": 5, "inherent_i": 5, "curr_l": 2, "curr_i": 3
            },
            {
                "dept_id": 3,
                "dept_code": "HSSE",
                "risk_id": "RSK-HSSE-002",
                "risk_name": "Tank Farm High Pressure Firewater Ring Main Header Rupture",
                "description": "Subsurface external microbial corrosion on underground 16-inch carbon steel firewater ring header risking pressure loss during firefighting.",
                "mitigation": "Conduct inline ultrasonic pigging, install sectional isolation motorized valves, and upgrade sacrificial anode cathodic protection.",
                "owner_id": 11,
                "action_owner_id": 12,
                "risk_status": 2,  # Submitted -> Pending FH Approval
                "fh_status": 0,
                "fh_remark": None,
                "fh_by": None,
                "rm_status": None,
                "rm_remark": None,
                "rm_by": None,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Perform hydrotesting of segmented firewater sections and replace 250m corroded carbon steel with HDPE.",
                "target_date": (now + timedelta(days=90)).strftime("%Y-%m-%d"),
                "progress": 20,
                "inherent_l": 4, "inherent_i": 5, "curr_l": 2, "curr_i": 3
            },
            {
                "dept_id": 3,
                "dept_code": "HSSE",
                "risk_id": "RSK-HSSE-003",
                "risk_name": "Effluent Treatment Plant (ETP) Biological Basin Shock Load & Environmental Non-Compliance",
                "description": "Sudden phenolic wastewater discharge from crude desalters overwhelming aerated lagoons and leading to COD limit breach in marine discharge.",
                "mitigation": "Install upstream TOC analyzer, emergency diversion slop equalization basin, and bio-augmentation dosing culture.",
                "owner_id": 11,
                "action_owner_id": 12,
                "risk_status": 5,  # Risk Head Approved (Final Approved)
                "fh_status": 1,
                "fh_remark": "Approved by HSE Functional Head.",
                "fh_by": 10,
                "rm_status": 1,
                "rm_remark": "Environmental compliance controls are robust.",
                "rm_by": 3,
                "rh_status": 1,
                "rh_remark": "Final governance sign-off completed by CRO / Risk Head.",
                "rh_by": 2,
                "action_plan": "Construct automated diverter gate to route high-COD stream to temporary holding tank 502.",
                "target_date": (now + timedelta(days=45)).strftime("%Y-%m-%d"),
                "progress": 85,
                "inherent_l": 4, "inherent_i": 4, "curr_l": 1, "curr_i": 2
            },

            # --- Department 4: Maintenance & Engineering (MAINT) ---
            {
                "dept_id": 4,
                "dept_code": "MAINT",
                "risk_id": "RSK-MAINT-001",
                "risk_name": "Critical Gas Turbine Generator (GTG-1) High Vibration and Bearing Fatigue",
                "description": "Unbalance in power turbine rotor bearing #2 leading to trip of primary captive power generation and blackout risk.",
                "mitigation": "Implement continuous condition monitoring via Bently Nevada 3500 rack, dynamic balancing, and synthetic turbine oil sampling.",
                "owner_id": 14,
                "action_owner_id": 15,
                "risk_status": 3,  # Function Head Approved -> Pending RM Approval
                "fh_status": 1,
                "fh_remark": "Turbine overhaul scope approved.",
                "fh_by": 13,
                "rm_status": None,
                "rm_remark": None,
                "rm_by": None,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Perform in-situ dynamic balancing and replace tilting-pad journal bearing assembly.",
                "target_date": (now + timedelta(days=20)).strftime("%Y-%m-%d"),
                "progress": 45,
                "inherent_l": 4, "inherent_i": 5, "curr_l": 2, "curr_i": 3
            },
            {
                "dept_id": 4,
                "dept_code": "MAINT",
                "risk_id": "RSK-MAINT-002",
                "risk_name": "High Pressure Steam Boiler Superheater Tube Rupture",
                "description": "Long-term thermal creep and scale deposition on boiler tube bends leading to pinhole steam leak and plant steam header depressurization.",
                "mitigation": "Conduct phased-array ultrasonic testing (PAUT) during annual shutdown, strict demineralized water chemistry control, and sootblower optimization.",
                "owner_id": 14,
                "action_owner_id": 15,
                "risk_status": 2,  # Submitted -> Pending FH Approval
                "fh_status": 0,
                "fh_remark": None,
                "fh_by": None,
                "rm_status": None,
                "rm_remark": None,
                "rm_by": None,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Replace 48 superheater pendant tube elements with SA-213 T91 alloy tubing.",
                "target_date": (now + timedelta(days=50)).strftime("%Y-%m-%d"),
                "progress": 20,
                "inherent_l": 4, "inherent_i": 4, "curr_l": 2, "curr_i": 2
            },
            {
                "dept_id": 4,
                "dept_code": "MAINT",
                "risk_id": "RSK-MAINT-003",
                "risk_name": "Single Point Vulnerability on Heavy Crude Booster Pump VFD Drive",
                "description": "Aging variable frequency drive (VFD) power electronics thyristors lacking OEM vendor support, posing unmitigated pumping loss.",
                "mitigation": "Retrofit modern modular VFD with active front end (AFE), redundant cooling fans, and stocked IGBT power modules.",
                "owner_id": 14,
                "action_owner_id": 15,
                "risk_status": 4,  # Risk Manager Approved -> Pending RH Approval
                "fh_status": 1,
                "fh_remark": "Approved for Capex replacement program.",
                "fh_by": 13,
                "rm_status": 1,
                "rm_remark": "Supply chain and turnaround timeline verified.",
                "rm_by": 3,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Execute factory acceptance test (FAT) and commissioning of new 6.6kV ABB VFD cubicle.",
                "target_date": (now + timedelta(days=40)).strftime("%Y-%m-%d"),
                "progress": 70,
                "inherent_l": 4, "inherent_i": 4, "curr_l": 1, "curr_i": 2
            },

            # --- Department 5: Finance & Commercial (FIN) ---
            {
                "dept_id": 5,
                "dept_code": "FIN",
                "risk_id": "RSK-FIN-001",
                "risk_name": "Crude Feedstock Price Volatility & Crack Spread Margin Squeeze",
                "description": "Sharp geopolitical shifts in Brent/Dubai crude differentials and refined product crack spreads impacting gross refining margin (GRM).",
                "mitigation": "Establish dynamic commodity derivative hedging mandate with ±15% collar limits, weekly treasury risk committee reviews, and multi-supplier crude contracts.",
                "owner_id": 17,
                "action_owner_id": 18,
                "risk_status": 3,  # Function Head Approved -> Pending RM Approval
                "fh_status": 1,
                "fh_remark": "Hedging policy governance aligned with board guidelines.",
                "fh_by": 16,
                "rm_status": None,
                "rm_remark": None,
                "rm_by": None,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Execute automated crack spread swap hedges on ICE/NYMEX for Q3/Q4 crude volume quotas.",
                "target_date": (now + timedelta(days=25)).strftime("%Y-%m-%d"),
                "progress": 60,
                "inherent_l": 5, "inherent_i": 5, "curr_l": 2, "curr_i": 3
            },
            {
                "dept_id": 5,
                "dept_code": "FIN",
                "risk_id": "RSK-FIN-002",
                "risk_name": "Foreign Exchange (USD/INR) Exposure on Heavy Equipment Import Contracts",
                "description": "Unhedged foreign currency capex liabilities for imported European refinery column internals exposing project to forex depreciation.",
                "mitigation": "Lock in forward exchange contracts (FEC) matching milestone payment milestones and maintain EEFC foreign currency reserve account.",
                "owner_id": 17,
                "action_owner_id": 18,
                "risk_status": 2,  # Submitted -> Pending FH Approval
                "fh_status": 0,
                "fh_remark": None,
                "fh_by": None,
                "rm_status": None,
                "rm_remark": None,
                "rm_by": None,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Book USD 12M forward currency cover with consortium banks for EPC stage payment.",
                "target_date": (now + timedelta(days=30)).strftime("%Y-%m-%d"),
                "progress": 35,
                "inherent_l": 4, "inherent_i": 4, "curr_l": 2, "curr_i": 2
            },
            {
                "dept_id": 5,
                "dept_code": "FIN",
                "risk_id": "RSK-FIN-003",
                "risk_name": "Offtaker Default and Counterparty Credit Concentration Risk",
                "description": "High credit exposure to single bulk petrochemical offtakers under 60-day credit terms risking working capital impairment.",
                "mitigation": "Enforce irrevocable bank letters of credit (LCs), credit rating thresholds, and daily credit limit validation in SAP ERP.",
                "owner_id": 17,
                "action_owner_id": 18,
                "risk_status": 4,  # Risk Manager Approved -> Pending RH Approval
                "fh_status": 1,
                "fh_remark": "Credit monitoring guidelines verified.",
                "fh_by": 16,
                "rm_status": 1,
                "rm_remark": "Counterparty credit review complete.",
                "rm_by": 3,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Implement real-time trade credit insurance policy for all non-LC industrial offtakers.",
                "target_date": (now + timedelta(days=45)).strftime("%Y-%m-%d"),
                "progress": 55,
                "inherent_l": 4, "inherent_i": 4, "curr_l": 1, "curr_i": 2
            },

            # --- Department 6: Information Technology & SCADA (IT) ---
            {
                "dept_id": 6,
                "dept_code": "IT",
                "risk_id": "RSK-IT-001",
                "risk_name": "SCADA / Industrial Control System (ICS) Ransomware & OT Network Intrusion",
                "description": "Potential breach of IT-OT air-gap firewall allowing lateral malware propagation to programmable logic controllers (PLCs) and safety instrumented systems (SIS).",
                "mitigation": "Implement IEC 62443 zone segmentation, unidirectional data diodes for historian replication, multi-factor authentication (MFA) on all jump hosts, and 24/7 OT SOC monitoring.",
                "owner_id": 20,
                "action_owner_id": 21,
                "risk_status": 3,  # Function Head Approved -> Pending RM Approval
                "fh_status": 1,
                "fh_remark": "Cybersecurity posture and diode deployment approved.",
                "fh_by": 19,
                "rm_status": None,
                "rm_remark": None,
                "rm_by": None,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Commission Nozomi Networks OT network anomaly monitoring and dual redundant hardware data diodes.",
                "target_date": (now + timedelta(days=35)).strftime("%Y-%m-%d"),
                "progress": 40,
                "inherent_l": 5, "inherent_i": 5, "curr_l": 2, "curr_i": 3
            },
            {
                "dept_id": 6,
                "dept_code": "IT",
                "risk_id": "RSK-IT-002",
                "risk_name": "Cloud ERP & Disaster Recovery Site Synchronization Latency",
                "description": "Primary to DR site data replication delay exceeding RPO (Recovery Point Objective) of 15 minutes during subsea optical cable disruptions.",
                "mitigation": "Establish dual redundant SD-WAN links across Tier-3 data centers, automate failover orchestration, and conduct biannual DR drills.",
                "owner_id": 20,
                "action_owner_id": 21,
                "risk_status": 2,  # Submitted -> Pending FH Approval
                "fh_status": 0,
                "fh_remark": None,
                "fh_by": None,
                "rm_status": None,
                "rm_remark": None,
                "rm_by": None,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Implement AWS/Azure Cloud DR active-active asynchronous database replication pipeline.",
                "target_date": (now + timedelta(days=60)).strftime("%Y-%m-%d"),
                "progress": 25,
                "inherent_l": 4, "inherent_i": 4, "curr_l": 2, "curr_i": 2
            },
            {
                "dept_id": 6,
                "dept_code": "IT",
                "risk_id": "RSK-IT-003",
                "risk_name": "Privileged Access Management (PAM) Compromise across Enterprise Domain Controllers",
                "description": "Unauthorized elevation of administrative credentials leading to unauthorized Active Directory schema changes and enterprise service disruption.",
                "mitigation": "Deploy CyberArk PAM vault, enforce ephemeral just-in-time (JIT) access tokens, and mandate FIDO2 hardware security keys for all administrators.",
                "owner_id": 20,
                "action_owner_id": 21,
                "risk_status": 4,  # Risk Manager Approved -> Pending RH Approval
                "fh_status": 1,
                "fh_remark": "PAM architecture review completed.",
                "fh_by": 19,
                "rm_status": 1,
                "rm_remark": "Governance and privileged identity controls verified.",
                "rm_by": 3,
                "rh_status": None,
                "rh_remark": None,
                "rh_by": None,
                "action_plan": "Enforce mandatory PAM check-in/check-out vaulting for all domain controllers and network switches.",
                "target_date": (now + timedelta(days=20)).strftime("%Y-%m-%d"),
                "progress": 65,
                "inherent_l": 5, "inherent_i": 5, "curr_l": 1, "curr_i": 2
            }
        ]

        print(f"2. Seeding {len(risks_data)} enterprise risks...")

        dept_max_numbers = {}
        reg_id_counter = 1
        desc_id_counter = 1
        treat_id_counter = 1

        for item in risks_data:
            d_id = item["dept_id"]
            dept_max_numbers[d_id] = dept_max_numbers.get(d_id, 0) + 1

            fh_on = now_str if item["fh_status"] == 1 else None
            rm_on = now_str if item["rm_status"] == 1 else None
            rh_on = now_str if item["rh_status"] == 1 else None

            reg_id = reg_id_counter
            reg_id_counter += 1

            desc_id = desc_id_counter
            desc_id_counter += 1

            treat_id = treat_id_counter
            treat_id_counter += 1

            # Insert risk_register
            cur.execute(f"""
                INSERT INTO {DB_SCHEMA}.risk_register (
                    risk_register_id, risk_id, risk_name, dept_id, risk_owner_id, financial_year,
                    risk_status, risk_progress,
                    risk_function_head_approval_status, risk_function_head_approval_remark, risk_function_head_approval_on, risk_function_head_approval_by,
                    risk_manager_approval_status, risk_manager_approval_remark, risk_manager_approved_on, risk_manager_approval_by,
                    risk_head_approval_status, risk_head_approval_remark, risk_head_approved_on, risk_head_approval_by,
                    created_by, created_on, modified_by, modified_on, is_active, is_deleted
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, 1, 0
                );
            """, [
                reg_id, item["risk_id"], item["risk_name"], d_id, item["owner_id"], "2026-2027",
                item["risk_status"], item["progress"],
                item["fh_status"], item["fh_remark"], fh_on, item["fh_by"],
                item["rm_status"], item["rm_remark"], rm_on, item["rm_by"],
                item["rh_status"], item["rh_remark"], rh_on, item["rh_by"],
                item["owner_id"], now_str, item["owner_id"], now_str
            ])

            # Insert risk_description
            cur.execute(f"""
                INSERT INTO {DB_SCHEMA}.risk_description (
                    risk_description_id, risk_register_id, risk_id, risk_description, mitigation,
                    inherent_risk_likelihood_id, inherent_risk_impact_id,
                    current_risk_likelihood_id, current_risk_impact_id,
                    created_by, created_on, modified_by, modified_on, is_deleted
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, 0
                );
            """, [
                desc_id, reg_id, item["risk_id"], item["description"], item["mitigation"],
                item["inherent_l"], item["inherent_i"],
                item["curr_l"], item["curr_i"],
                item["owner_id"], now_str, item["owner_id"], now_str
            ])

            # Insert risk_treatment
            cur.execute(f"""
                INSERT INTO {DB_SCHEMA}.risk_treatment (
                    risk_treatment_id, risk_description_id, risk_register_id, risk_id, action_plan,
                    action_owner_id, target_date, progress, action_status_id,
                    created_on, created_by, modified_on, modified_by, is_deleted,
                    approval_status
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, 1,
                    %s, %s, %s, %s, 0,
                    1
                );
            """, [
                treat_id, desc_id, reg_id, item["risk_id"], item["action_plan"],
                item["action_owner_id"], item["target_date"], item["progress"],
                now_str, item["owner_id"], now_str, item["owner_id"]
            ])

            print(f"  -> Created [{item['risk_id']}] (Dept: {item['dept_code']}, Status: {item['risk_status']})")

        # Update last_risk_number for each department
        for dept_id, count in dept_max_numbers.items():
            cur.execute(f"UPDATE {DB_SCHEMA}.mst_department SET last_risk_number = %s WHERE id = %s;", [count, dept_id])

        conn.commit()
        print("\nAll risk tables truncated and freshly seeded successfully!")
        return True

    except Exception as e:
        conn.rollback()
        print(f"Error seeding data: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    reset_and_seed_data()
