"""
Static and Contextual Suggestion Providers for Risk Creation.
"""
from __future__ import annotations

from typing import List, Optional, Protocol


class RiskSuggestionProvider(Protocol):
    """Protocol for Risk Suggestion Providers (Static now, AI/Agentic RAG in future)."""
    def get_description_suggestions(self, title: str, category: Optional[str] = None) -> List[str]: ...
    def get_mitigation_suggestions(self, title: str, category: Optional[str] = None) -> List[str]: ...
    def get_action_plan_suggestions(self, title: str, mitigation: Optional[str] = None) -> List[str]: ...


class StaticRiskSuggestionProvider:
    """
    Static Suggestion Provider returning 2-4 curated recommendations
    for Risk Description, Mitigation Strategy, and Action Plan.
    Cleanly isolated so it can be swapped with AgenticRAGSuggestionProvider in future phases.
    """

    @staticmethod
    def _detect_category(title: str) -> str:
        lower = (title or "").lower()
        if any(w in lower for w in ["pump", "gas", "leak", "valve", "compressor", "seal", "containment"]):
            return "PUMP_GAS_LEAK"
        elif any(w in lower for w in ["corrosion", "pipe", "crude", "h2s", "column", "metallurgy", "pipeline"]):
            return "CORROSION_METALLURGY"
        elif any(w in lower for w in ["power", "electrical", "transformer", "cable", "motor", "switchgear", "grid"]):
            return "ELECTRICAL_POWER"
        elif any(w in lower for w in ["fire", "explosion", "flammable", "flare", "boiler"]):
            return "FIRE_SAFETY"
        return "GENERAL_OPERATIONAL"

    def get_description_suggestions(self, title: str, category: Optional[str] = None) -> List[str]:
        cat = category or self._detect_category(title)
        if cat == "PUMP_GAS_LEAK":
            return [
                f"Identified operational hazard: {title}. Mechanical seal degradation leading to hydrocarbon containment loss and ambient VOC release.",
                f"Process safety risk on {title} due to suction pressure oscillations, thermal fatigue, and barrier fluid contamination.",
                f"Equipment integrity hazard: {title} exhibiting high vibration, seal face blistering, and potential flammable gas leak."
            ]
        elif cat == "CORROSION_METALLURGY":
            return [
                f"Localized internal wall thinning on {title} caused by high H2S wet acid gas corrosion and turbulence.",
                f"Severe pitting and galvanic corrosion on {title} exceeding allowable corrosion allowance with risk of breach.",
                f"Structural metallurgy degradation on {title} due to amine stress corrosion cracking and temperature swings."
            ]
        elif cat == "ELECTRICAL_POWER":
            return [
                f"Dielectric breakdown and partial discharge in {title} risking unannounced total substation trip.",
                f"Overheating of terminal lugs and insulation aging on {title} leading to potential arc flash hazard.",
                f"Redundancy failure risk on {title} auxiliary UPS inverter bank causing critical DCS blackout."
            ]
        elif cat == "FIRE_SAFETY":
            return [
                f"Flammable inventory accumulation and ignition potential near {title} requiring enhanced deluge protection.",
                f"Overpressure excursion in {title} relief header risking thermal radiation exposure and safety valve chatter."
            ]
        else:
            return [
                f"Operational vulnerability in {title} causing process disruption, throughput loss, and safety compliance deviation.",
                f"Asset reliability risk on {title} arising from component wear, duty-cycle fatigue, and unmitigated vibration.",
                f"Operational risk: {title} requiring structured maintenance governance, root cause isolation, and barrier controls."
            ]

    def get_mitigation_suggestions(self, title: str, category: Optional[str] = None) -> List[str]:
        cat = category or self._detect_category(title)
        if cat == "PUMP_GAS_LEAK":
            return [
                f"Isolate suction/discharge valves, depressurize, and replace mechanical seal with API 682 Plan 53B dual seal on {title}.",
                "Install optical infrared (IR) gas detection sensor with DCS automated Emergency Shutdown (ESD) interlock.",
                "Perform ultrasonic wall thickness scanning on adjoining spool and implement weekly LDAR sniffer rounds."
            ]
        elif cat == "CORROSION_METALLURGY":
            return [
                "Replace carbon steel pipe spool with 13Cr-Mo alloy metallurgy and install MDEA inhibitor injection skid.",
                "Online real-time H2S monitoring with DCS alarm set at 5 ppm and weekly corrosion coupon measurement.",
                "Ultrasonic phased array inspection on high-turbulent elbow sections and baseline radiography."
            ]
        elif cat == "ELECTRICAL_POWER":
            return [
                "Deploy continuous partial discharge monitoring and thermal imaging surveillance on high-voltage connections.",
                "Install redundant dual-feed automatic transfer switch (ATS) with automated isolation breaker trips.",
                "Execute complete dielectric oil testing (DGA) and schedule certified busbar torque verification."
            ]
        elif cat == "FIRE_SAFETY":
            return [
                "Install high-speed ultraviolet/infrared flame detectors linked to automatic deluge skid actuation.",
                "Upgrade passive fireproofing insulation (PFP) to 2-hour hydrocarbon pool fire rating."
            ]
        else:
            return [
                f"Implement immediate engineering isolation, containment, and certified component overhaul for {title}.",
                "Upgrade automated instrumentation thresholds and DCS alarm trips with fail-safe interlocks.",
                "Conduct comprehensive non-destructive testing (NDT) and schedule routine preventative maintenance."
            ]

    def get_action_plan_suggestions(self, title: str, mitigation: Optional[str] = None) -> List[str]:
        return [
            f"Phase 1: Mobilize maintenance crew for physical barrier isolation and component overhaul within 14 days.",
            f"Phase 2: Procure certified replacement parts, calibrate DCS trip interlocks, and perform leak testing within 30 days.",
            f"Phase 3: Update plant preventive maintenance SOP, conduct NDT baseline logging, and complete sign-off in 45 days."
        ]


# Singleton static suggestion provider instance
static_suggestion_provider = StaticRiskSuggestionProvider()
